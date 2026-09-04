/**
 * TaskBot Mini App - Frontend Logic
 */

const tg = window.Telegram?.WebApp;
const API_BASE = '/api';

const IC = {
    new:        `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
    progress:   `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`,
    review:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
    done:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>`,
    overdue:    `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    cancelled:  `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    fire:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8.5 14.5A2.5 2.5 0 0011 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 01-7 7 6.998 6.998 0 01-6-3.49M14.5 18.5a2.5 2.5 0 01-5 0"/></svg>`,
    clock:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    play:       `<svg class="ic" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
    check:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>`,
    xmark:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    send:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
    attach:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>`,
    star:       `<svg class="ic" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
    eye:        `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
    refresh:    `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
    low:        `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`,
    medium:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    high:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>`,
    urgent:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    plus:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    step:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 012 2v7"/><line x1="6" y1="9" x2="6" y2="21"/></svg>`,
    file:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
    pause:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
    circle:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`,
    copy:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
    share:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`,
    user:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    calendar:   `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    comment:    `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`,
    building:   `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/></svg>`,
    team:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>`,
    bolt:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
    pin:        `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>`,
    edit:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
    folder:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`,
    chart:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
    trend:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>`,
    clipboard:  `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
    flag:       `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`,
    puzzle:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.24 12.24a6 6 0 00-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/></svg>`,
    donut:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/></svg>`,
    upload:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/></svg>`,
    image:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
    shield:     `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    crown:      `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 20h20M5 20l2-8 5 4 5-4 2 8"/><circle cx="5" cy="10" r="1" fill="currentColor"/><circle cx="12" cy="6" r="1" fill="currentColor"/><circle cx="19" cy="10" r="1" fill="currentColor"/></svg>`,
};

/**
 * URL dagi ?token= parametrini bir marta o'qib saqlaymiz.
 * Telegram Desktop da initData bo'lmaganda fallback sifatida ishlatiladi.
 */
const _URL_AUTH_TOKEN = (() => {
    try {
        return new URLSearchParams(window.location.search).get('token') || '';
    } catch (e) { return ''; }
})();

/**
 * initData ni olish — Telegram Desktop da URL hash dan olinadi.
 * SDK da bo'lmasa, window.location.hash ichidagi tgWebAppData ni ishlatadi.
 */
function getInitData() {
    // 1) SDK orqali (mobil Telegram) — har doim window.Telegram dan yangi o'qiymiz
    const initD = window.Telegram?.WebApp?.initData;
    if (initD) return initD;
    // 2) URL hash orqali (Telegram Desktop / ba'zi versiyalar)
    try {
        const hash = window.location.hash.slice(1);
        const params = new URLSearchParams(hash);
        const data = params.get('tgWebAppData');
        if (data) return decodeURIComponent(data);
    } catch (e) { /* ignore */ }
    return '';
}

/**
 * API so'rovlar uchun auth headerlarini qo'shadi.
 * initData → X-Telegram-Init-Data
 * token → X-Auth-Token (Telegram Desktop fallback)
 */
function applyAuthHeaders(headers) {
    const id = getInitData();
    if (id) {
        headers['X-Telegram-Init-Data'] = id;
    } else if (_URL_AUTH_TOKEN) {
        headers['X-Auth-Token'] = _URL_AUTH_TOKEN;
    }
}

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
        applyAuthHeaders(headers);
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
        applyAuthHeaders(headers);
        const res = await fetch(API_BASE + '/i18n/set-lang', {
            method: 'POST',
            headers,
            body: JSON.stringify({ lang }),
        });
        if (!res.ok) throw new Error('http ' + res.status);
        const data = await res.json();
        I18N.lang = data.lang;
        I18N.dict = data.translations || {};

        // 1) data-i18n atributli statik elementlar
        applyI18n();

        // 2) Til tugmalarini yangilash
        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.lang === I18N.lang);
        });

        // 3) Barcha dinamik kontentni qayta render qilamiz
        await reRenderAllUI();

        if (typeof showToast === 'function') showToast(tr('common.success') || '✓');
    } catch (e) {
        console.warn('set lang failed:', e);
        if (typeof showToast === 'function') showToast('❌ ' + e.message);
    }
}

/** Til o'zgargandan keyin butun UI ni qayta render qilish.
 * Bu funksiya statistikalar, vazifa kartochkalari, modal kontentni
 * va boshqa dinamik joylarni yangi tilda yangilaydi.
 */
async function reRenderAllUI() {
    try {
        // Header sarlavhasi (faol tab nomi)
        const titleMap = {
            tasks:    tr('app.tab.tasks')    || 'Vazifalar',
            calendar: tr('app.tab.calendar') || 'Kalendar',
            create:   tr('app.tab.create')   || 'Yangi vazifa',
            stats:    tr('app.tab.stats')    || 'Statistika',
            hujjatlar: tr('app.tab.docs')    || 'Hujjatlarim',
        };
        const activeTab = document.querySelector('.tab-pane.active')?.id?.replace('tab-', '');
        const hTitle = document.getElementById('header-title');
        if (hTitle && titleMap[activeTab]) hTitle.textContent = titleMap[activeTab];

        // Vazifalar ro'yxati va statistika — yangi til bilan API'dan tortib olamiz
        // (status badge va boshqa matnlar i18n bilan)
        if (typeof renderTasks === 'function') renderTasks();

        // Kartochka stats raqamlari uchun yangi labellar
        if (allTasks && typeof updateQuickStats === 'function') {
            try {
                const stats = await apiRequest(`/stats?company_id=${currentWorkspaceId}`);
                updateQuickStats(stats);
                if (typeof updateStatsTab === 'function') updateStatsTab(stats);
            } catch {}
        }

        // Calendar
        if (typeof renderCalendar === 'function') renderCalendar();

        // Statistika sahifasi (faol bo'lmasa ham labellarni yangilash uchun)
        if (typeof renderStatsCharts === 'function') {
            try { renderStatsCharts(_statsLastData); } catch {}
        }

        // Hujjatlar (employee) sahifasi ochiq bo'lsa
        if (typeof empRender === 'function' && window._empAssignments) {
            try { empRender(window._empAssignments); } catch {}
        }

        // Ochiq modal bo'lsa — yopib qayta ochish kerak emas, lekin matnlar yangilanmasligi mumkin
        // Foydalanuvchi modalni yopib qaytadan ochsa hammasi yangi tilda chiqadi
    } catch (e) {
        console.warn('reRenderAllUI failed:', e);
    }
}
let currentFilter = 'active';
let allTasks = [];
let currentTaskId = null;
// Sub-task mode state
let _subtaskParentId    = null;
let _subtaskParentTitle = null;
let currentWorkspaceId = 'all';
let currentWorkspaceName = 'Hammasi';
let companyMembers = [];
let selectedAssigneeIds = [];
let externalAssignees = [];      // [{id,name,role,group_id,group_name}] — boshqa guruhdan
let selectedResponsibleIds = []; // mas'ul shaxslar ID lari (ko'p tanlash)
let _allWorkspaces = [];          // cache: [{id,name}]
let statusChart = null;
let membersChart = null;
let priorityChart = null;
let trendChart = null;
let overdueChart = null;

// ===== Calendar State =====
let calendarDate = new Date();   // currently viewed month
let selectedCalDate = null;      // 'YYYY-MM-DD' string

// ===== Theme =====
const APP_MOON_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>`;
const APP_SUN_SVG  = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;

function appApplyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('app-theme-btn');
    if (btn) {
        btn.innerHTML = theme === 'light' ? APP_MOON_SVG : APP_SUN_SVG;
        btn.title = theme === 'light' ? "Qorong'i rejim" : "Yorug' rejim";
    }
    if (tg) {
        const bgColor = theme === 'light' ? '#f4f4f9' : '#0A0A14';
        try { tg.setHeaderColor(bgColor); } catch(e) {}
        try { tg.setBackgroundColor(bgColor); } catch(e) {}
    }
}

function appToggleTheme() {
    const current = localStorage.getItem('app_theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('app_theme', next);
    appApplyTheme(next);
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

// ============================================================
//  SILENT REFRESH + AUTO POLLING + MANUAL BUTTON
// ============================================================
let _refreshing = false;
let _autoRefreshInterval = null;
const AUTO_REFRESH_MS = 10000;   // 10 soniya

// Vazifalar ro'yxati uchun "barmoq izi" — o'zgarish borligini aniqlash uchun
function _tasksFingerprint(tasks) {
    return (tasks || [])
        .map(t => `${t.id}:${t.status}:${t.priority}:${t.completed_at||''}:${t.updated_at||t.created_at||''}:${(t.assignees||[]).map(a=>a.id+'/'+a.status+'/'+(a.is_responsible?'1':'0')).join(',')}:${(t.comments_count||0)}:${(t.attachments_count||0)}`)
        .join('|');
}
let _lastTasksFingerprint = '';
let _lastStatsFingerprint = '';

async function silentRefresh(opts = {}) {
    if (_refreshing) return;
    _refreshing = true;
    const { showToastOnNew = false, showSpinner = false, force = false } = opts;
    const btn = document.getElementById('app-refresh-btn');
    if (showSpinner && btn) btn.classList.add('refreshing');
    try {
        const [tasksData, statsData] = await Promise.all([
            apiRequest(`/tasks?company_id=${currentWorkspaceId}`),
            apiRequest(`/stats?company_id=${currentWorkspaceId}`),
        ]);
        const prevIds = new Set(allTasks.map(t => t.id));
        const newTasks = tasksData.tasks || [];
        const added = newTasks.filter(t => !prevIds.has(t.id)).length;

        // Diff tekshiruvi — agar hech narsa o'zgarmagan bo'lsa, render qilmaymiz
        const newFp = _tasksFingerprint(newTasks);
        const newStatsFp = JSON.stringify(statsData || {});
        const tasksChanged = force || newFp !== _lastTasksFingerprint;
        const statsChanged = force || newStatsFp !== _lastStatsFingerprint;

        allTasks = newTasks;

        if (statsChanged) {
            _lastStatsFingerprint = newStatsFp;
            try { updateQuickStats(statsData); } catch(e){}
            try { updateStatsTab(statsData); } catch(e){}
        }

        if (tasksChanged) {
            _lastTasksFingerprint = newFp;
            try { renderTasks(); } catch(e){}
            try { renderCalendar?.(); } catch(e){}
        }

        if (showToastOnNew && added > 0) {
            showToast(`📥 ${added} ta yangi vazifa`);
            if (tg) tg.HapticFeedback?.notificationOccurred('success');
        }
    } catch (e) {
        console.warn('silentRefresh:', e?.message || e);
    } finally {
        _refreshing = false;
        if (showSpinner && btn) setTimeout(() => btn.classList.remove('refreshing'), 400);
    }
}

async function manualRefresh() {
    FX.refresh();
    await silentRefresh({ showSpinner: true });
    showToast('✓ Yangilandi');
}

function startAutoRefresh() {
    stopAutoRefresh();
    _autoRefreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible') {
            silentRefresh({ showToastOnNew: true });   // animatsiyasiz
        }
    }, AUTO_REFRESH_MS);
}

function stopAutoRefresh() {
    if (_autoRefreshInterval) {
        clearInterval(_autoRefreshInterval);
        _autoRefreshInterval = null;
    }
}

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        silentRefresh({ showToastOnNew: true });  // tab'ga qaytganda — animatsiyasiz
    }
});

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    // Apply saved theme first
    const savedTheme = localStorage.getItem('app_theme') || 'dark';
    appApplyTheme(savedTheme);

    if (tg) {
        tg.ready();
        tg.expand();
        try {
            // Bot API 8.0+ — to'liq ekran
            if (typeof tg.requestFullscreen === 'function') {
                tg.requestFullscreen();
            }
            // Bot API 7.7+ — vertical swipe'ni o'chirish (modal yopilib ketmasligi uchun)
            if (typeof tg.disableVerticalSwipes === 'function') {
                tg.disableVerticalSwipes();
            }
        } catch (e) { /* eski Telegram versiyasi — sukut */ }

        // Safe area — yuqori Telegram tugmalar bilan to'qnashmasin (notch, statusbar, ⋯ tugma)
        const _applySafeArea = () => {
            try {
                const cs = tg.contentSafeAreaInset || tg.safeAreaInset || {};
                const top = Math.max(0, Number(cs.top || 0));
                document.documentElement.style.setProperty('--tg-safe-t', top + 'px');
            } catch(_) {}
        };
        _applySafeArea();
        try {
            if (typeof tg.onEvent === 'function') {
                tg.onEvent('contentSafeAreaChanged', _applySafeArea);
                tg.onEvent('safeAreaChanged',         _applySafeArea);
                tg.onEvent('viewportChanged',         _applySafeArea);
                tg.onEvent('fullscreenChanged',       _applySafeArea);
            }
        } catch(_) {}

        tg.enableClosingConfirmation();

        if (savedTheme === 'dark') {
            // Force dark theme — override any Telegram light theme vars
            document.body.style.setProperty('--tg-theme-bg-color',          '#0A0A14');
            document.body.style.setProperty('--tg-theme-secondary-bg-color','#11111E');
            document.body.style.setProperty('--tg-theme-text-color',         '#EEEEF8');
            document.body.style.setProperty('--tg-theme-hint-color',         '#9090B0');
            document.body.style.setProperty('--tg-theme-link-color',         '#6366F1');
            document.body.style.setProperty('--tg-theme-button-color',       '#6366F1');
            document.body.style.setProperty('--tg-theme-button-text-color',  '#FFFFFF');
        }
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
        applyAuthHeaders(headers);
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
    
    applyAuthHeaders(headers);

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

// ===== Loading progress helpers =====
function _ldSetPercent(p, status) {
    p = Math.max(0, Math.min(100, Math.round(p)));
    const fill = document.getElementById('ld-bar-fill');
    const pct  = document.getElementById('ld-percent');
    const st   = document.getElementById('ld-status');
    if (fill) fill.style.width = p + '%';
    if (pct)  pct.textContent  = p + '%';
    if (st && status) st.textContent = status;
}
function _ldStep(key, state) {
    // state: 'active' | 'done'
    const el = document.querySelector(`.ld-step[data-step="${key}"]`);
    if (!el) return;
    el.classList.remove('active', 'done');
    el.classList.add(state);
}

// ===== Load App =====
// Har bosqichni kamida shu vaqt ko'rsatish (sun'iy pauza, jami ~2s) —
// API tez ishlasa ham foydalanuvchi premium animatsiyani ko'radi.
const _LD_MIN_MS = 500;
const _sleep = ms => new Promise(r => setTimeout(r, ms));
async function _withMin(stepKey, work) {
    const t0 = Date.now();
    _ldStep(stepKey, 'active');
    const result = await work();
    const elapsed = Date.now() - t0;
    if (elapsed < _LD_MIN_MS) await _sleep(_LD_MIN_MS - elapsed);
    _ldStep(stepKey, 'done');
    return result;
}

async function loadApp() {
    try {
        const urlParams = new URLSearchParams(window.location.search);

        // 1) Auth
        _ldSetPercent(8, "Avtorizatsiya tekshirilmoqda…");
        await _withMin('auth', async () => { /* token / initData allaqachon o'qilgan */ });

        // 2) Workspace
        _ldSetPercent(28, "Workspace yuklanmoqda…");
        const wsData = await _withMin('ws', () => apiRequest('/workspaces'));

        // 3) Tasks
        _ldSetPercent(55, "Vazifalar yuklanmoqda…");
        const tasksData = await _withMin('tasks', () =>
            apiRequest(`/tasks?company_id=${currentWorkspaceId}`)
        );

        // 4) Stats
        _ldSetPercent(82, "Statistika yuklanmoqda…");
        const statsData = await _withMin('stats', () =>
            apiRequest(`/stats?company_id=${currentWorkspaceId}`)
        );

        _ldSetPercent(94, "Interfeysni tayyorlash…");

        // Populate custom workspace picker
        if (wsData.workspaces) {
            window._allWorkspaces = wsData.workspaces;  // create-form uchun
            _populateWsPicker(wsData.workspaces, currentWorkspaceId);
        }
        updateCreateWorkspaceUI();

        allTasks = tasksData.tasks || [];
        window._myUserId = tasksData.user_id || null;

        // User info — Telegram dan to'g'ridan-to'g'ri olamiz (har kim o'zini ko'radi)
        const tgUser = tg?.initDataUnsafe?.user;
        const userName = tgUser?.first_name
            ? (tgUser.last_name ? `${tgUser.first_name} ${tgUser.last_name}` : tgUser.first_name)
            : (tasksData.user_name || 'Foydalanuvchi');
        window._currentUserName = userName;
        // Eski header-name element bo'lsa yangilaymiz (backward compat)
        const oldNameEl = document.getElementById('user-name');
        if (oldNameEl) oldNameEl.textContent = `Salom, ${userName}!`;
        const avatarEl = document.getElementById('user-avatar');
        avatarEl.textContent = userName.charAt(0).toUpperCase();
        avatarEl.style.backgroundImage = '';
        // photo_url — Telegram Mini App da har foydalanuvchi uchun o'ziga xos
        if (tgUser?.photo_url) {
            avatarEl.style.backgroundImage = `url('${tgUser.photo_url}')`;
            avatarEl.style.backgroundSize = 'cover';
            avatarEl.style.backgroundPosition = 'center';
            avatarEl.textContent = '';
            avatarEl.classList.add('avatar-loaded');
        } else {
            loadAvatar(avatarEl);
        }

        updateQuickStats(statsData);
        updateStatsTab(statsData);
        renderTasks();
        startCountdownTicker(); // Live countdown ticker
        startAutoRefresh();     // Har 10s da silent fetch
        checkAiStatus();        // AI yordamchi yoqilganmi — nav itemni ko'rsatish

        // Yakunlash
        _ldSetPercent(100, "Tayyor!");
        const loading = document.getElementById('loading-screen');
        // qisqa pauza — 100% to'liq ko'rinishi uchun
        setTimeout(() => {
            loading.classList.add('fade-out');
            setTimeout(() => {
                loading.classList.add('hidden');
                document.getElementById('app').classList.remove('hidden');
            }, 500);
        }, 280);
    } catch (err) {
        console.error('Load error:', err);
        const loading = document.getElementById('loading-screen');
        loading.classList.add('error');
        _ldSetPercent(100, "❗ Yuklashda xatolik. Qaytadan urinib ko'ring.");
        // Still show app after delay
        setTimeout(() => {
            document.getElementById('loading-screen').classList.add('hidden');
            document.getElementById('app').classList.remove('hidden');
        }, 2000);
    }
}

// ===== Leave Company/Workspace =====
async function leaveWorkspace(companyId) {
    if (!companyId || companyId === 'personal' || companyId === 'all') return;
    const confirmed = await new Promise(resolve => {
        if (tg?.showConfirm) {
            tg.showConfirm('Bu kompaniyadan chiqmoqchimisiz? Uning vazifalari ko\'rinmay qoladi.', resolve);
        } else {
            resolve(window.confirm('Bu kompaniyadan chiqmoqchimisiz?'));
        }
    });
    if (!confirmed) return;

    try {
        const r = await apiRequest(`/companies/${companyId}/leave`, 'DELETE');
        showToast('✅ Kompaniyadan chiqdingiz');
        // Reload workspaces
        window.location.reload();
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

// ================================================================
// CUSTOM WORKSPACE PICKER
// ================================================================

// Helper: derive a consistent gradient color from workspace name
function _wsGradient(name) {
    const palettes = [
        ['#6366F1','#8B5CF6'], ['#06B6D4','#6366F1'], ['#10B981','#06B6D4'],
        ['#F59E0B','#EF4444'], ['#EC4899','#8B5CF6'], ['#F97316','#F59E0B'],
        ['#14B8A6','#6366F1'], ['#8B5CF6','#EC4899'],
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0xffff;
    const [c1, c2] = palettes[hash % palettes.length];
    return `linear-gradient(135deg,${c1},${c2})`;
}

function _populateWsPicker(workspaces, activeId) {
    const dd = document.getElementById('ws-picker-dropdown');
    if (!dd) return;

    // Build items list: "Hammasi" first, then API workspaces
    const items = [{ id: 'all', name: 'Hammasi', isAll: true }]
        .concat(workspaces.map(w => ({ id: w.id, name: w.name, isAll: false })));

    // Build HTML (keep the arrow div, append options)
    const optionsHtml = items.map(w => {
        const isActive = String(w.id) === String(activeId);
        const initial = w.name.charAt(0).toUpperCase();
        const avatarCls = w.isAll ? 'ws-opt-av ws-opt-all' : 'ws-opt-av';
        const avatarStyle = w.isAll ? '' : ` style="background:${_wsGradient(w.name)}"`;
        const avatarContent = w.isAll ? '🌍' : initial;
        // Use data attributes — avoids quote-in-onclick issues
        const safeName = w.name.replace(/"/g, '&quot;');
        return `<div class="ws-option${isActive ? ' ws-opt-active' : ''}"
                     data-ws-id="${w.id}" data-ws-name="${safeName}"
                     onclick="selectWorkspace(this.dataset.wsId, this.dataset.wsName)">
            <div class="${avatarCls}"${avatarStyle}>${avatarContent}</div>
            <span class="ws-opt-name">${w.name}</span>
            <span class="ws-opt-check">✓</span>
        </div>`;
    }).join('');

    dd.innerHTML = '<div class="ws-picker-arrow"></div>' + optionsHtml;

    // Update button label
    const active = items.find(w => String(w.id) === String(activeId)) || items[0];
    _updateWsPickerBtn(active.name, active.isAll);
    currentWorkspaceName = active.name;
}

function _updateWsPickerBtn(name, isAll) {
    const dotEl  = document.getElementById('ws-picker-dot');
    const lblEl  = document.getElementById('ws-picker-label');
    if (!dotEl || !lblEl) return;
    if (isAll || name === 'Hammasi') {
        dotEl.textContent = '🌍';
        dotEl.style.background = 'linear-gradient(135deg,#06B6D4,#6366F1)';
        dotEl.style.fontSize = '13px';
    } else {
        dotEl.textContent = name.charAt(0).toUpperCase();
        dotEl.style.background = _wsGradient(name);
        dotEl.style.fontSize = '10px';
    }
    lblEl.textContent = name;
}

function toggleWsPicker() {
    const picker = document.getElementById('ws-picker');
    const dd     = document.getElementById('ws-picker-dropdown');
    if (!picker || !dd) return;
    if (picker.classList.contains('open')) {
        closeWsPicker();
    } else {
        dd.classList.remove('hidden');
        dd.classList.remove('ws-drop-close');
        // Force reflow so animation triggers fresh
        void dd.offsetWidth;
        picker.classList.add('open');
        dd.classList.add('ws-drop-open');
        if (tg) tg.HapticFeedback?.impactOccurred('light');
    }
}

function closeWsPicker() {
    const picker = document.getElementById('ws-picker');
    const dd     = document.getElementById('ws-picker-dropdown');
    if (!picker || !dd) return;
    picker.classList.remove('open');
    dd.classList.remove('ws-drop-open');
    dd.classList.add('ws-drop-close');
    setTimeout(() => {
        dd.classList.add('hidden');
        dd.classList.remove('ws-drop-close');
    }, 180);
}

function selectWorkspace(id, name) {
    // Update active state in list
    document.querySelectorAll('.ws-option').forEach(o =>
        o.classList.toggle('ws-opt-active', String(o.dataset.wsId) === String(id))
    );
    // Update button
    _updateWsPickerBtn(name, id === 'all');
    closeWsPicker();
    if (tg) tg.HapticFeedback?.selectionChanged();
    // Trigger data reload
    currentWorkspaceId = id;
    currentWorkspaceName = name;
    changeWorkspace(id, name);
}

// Close picker when clicking outside
document.addEventListener('click', function(e) {
    const picker = document.getElementById('ws-picker');
    if (picker && !picker.contains(e.target)) closeWsPicker();
});

// ===== Workspace Switcher =====
async function changeWorkspace(id, name) {
    // Accept direct args (from custom picker) or fall back to legacy
    if (id !== undefined) {
        currentWorkspaceId = id;
        currentWorkspaceName = name || 'Hammasi';
    }

    if (tg) tg.HapticFeedback?.selectionChanged();

    // Show/hide leave button
    const leaveBtn = document.getElementById('leave-workspace-btn');
    if (leaveBtn) {
        const isCompany = currentWorkspaceId !== 'personal' && currentWorkspaceId !== 'all';
        leaveBtn.classList.toggle('hidden', !isCompany);
        leaveBtn.onclick = () => leaveWorkspace(currentWorkspaceId);
    }

    updateCreateWorkspaceUI();

    // Workspace almashganda — eski kartalarni darrov tozalaymiz (stale ko'rinmasin)
    allTasks = [];
    const _tl = document.getElementById('task-list');
    if (_tl) _tl.innerHTML = '';

    try {
        // Pass company_id parameter (supports 'all' for all workspaces)
        const queryParam = currentWorkspaceId === 'all' ? 'all' : currentWorkspaceId;

        const [tasksData, statsData] = await Promise.all([
            apiRequest(`/tasks?company_id=${queryParam}`),
            apiRequest(`/stats?company_id=${queryParam}`),
        ]);

        allTasks = tasksData.tasks || [];
        _kanbanMemberId = null;  // workspace o'zgarganda filter reset
        updateQuickStats(statsData);
        updateStatsTab(statsData);
        renderTasks();

        // Kanban tabi ochiq bo'lsa yangilaymiz
        const kanbanTab = document.getElementById('tab-kanban');
        if (kanbanTab && kanbanTab.classList.contains('active')) {
            renderKanbanMemberBar();
            renderKanban();
        }

        // Reset calendar when switching workspaces
        selectedCalDate = null;
        const calTab = document.getElementById('tab-calendar');
        if (calTab && calTab.classList.contains('active')) {
            renderCalendar();
        }
    } catch(e) {
        showToast("Xatolik yuz berdi", true);
    }
}

// "Hammasi" da yaratayotganda — vaqtinchalik tanlangan workspace
let _createWsOverride = null;       // {id, name}
function _effectiveCreateWs() {
    if (currentWorkspaceId !== 'all') {
        return { id: currentWorkspaceId, name: currentWorkspaceName };
    }
    return _createWsOverride;  // null bo'lishi mumkin — tanlanmagan
}

function renderCreateWorkspacePicker() {
    const label = document.getElementById('create-workspace-label');
    if (!label) return;
    const all = window._allWorkspaces || [];
    const selected = _createWsOverride;

    if (selected) {
        label.classList.remove('ws-needs-pick');
        label.innerHTML = `${escapeHtml(selected.name)}
            <span style="margin-left:8px;color:var(--text3);font-size:11px">▼ o'zgartirish</span>`;
    } else {
        label.classList.add('ws-needs-pick');
        label.innerHTML = `⚠️ Workspace tanlang... <span style="color:var(--text3)">▼</span>`;
    }

    label.style.cursor = 'pointer';
    label.onclick = () => _openCreateWsPicker(all);
}

function _openCreateWsPicker(workspaces) {
    document.getElementById('cwp-overlay')?.remove();
    const items = (workspaces || []).filter(w => w.id !== 'all').map(w => `
        <button class="cwp-item${_createWsOverride?.id === w.id ? ' selected' : ''}"
                onclick="_pickCreateWs('${w.id}','${(w.name||'').replace(/'/g,"\\'")}')">
            <span>${escapeHtml(w.name)}</span>
            ${_createWsOverride?.id === w.id ? '<span style="color:#22c55e">✓</span>' : ''}
        </button>
    `).join('');
    const el = document.createElement('div');
    el.id = 'cwp-overlay';
    el.className = 'cwp-overlay';
    el.innerHTML = `
        <div class="cwp-sheet">
            <div class="cwp-handle"></div>
            <div class="cwp-title">📁 Ishchi makon tanlang</div>
            <div class="cwp-sub">Vazifa qaerda yaratiladi?</div>
            <div class="cwp-list">${items || '<div style="color:var(--text3);padding:20px;text-align:center">Workspace yo\'q</div>'}</div>
            <button class="cwp-cancel" onclick="document.getElementById('cwp-overlay')?.remove()">Bekor qilish</button>
        </div>
    `;
    document.body.appendChild(el);
    el.addEventListener('click', e => { if (e.target === el) el.remove(); });
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

async function _pickCreateWs(wsId, wsName) {
    document.getElementById('cwp-overlay')?.remove();
    _createWsOverride = { id: wsId, name: wsName };
    if (tg) tg.HapticFeedback?.selectionChanged();
    await updateCreateWorkspaceUI();
}

async function updateCreateWorkspaceUI() {
    const label = document.getElementById('create-workspace-label');
    const group = document.getElementById('assignees-group');
    const list = document.getElementById('assignees-list');
    const hint = document.getElementById('assignees-hint');
    const submitBtn = document.getElementById('btn-create-task');

    selectedAssigneeIds = [];
    externalAssignees = [];
    selectedResponsibleIds = [];
    companyMembers = [];

    // "Hammasi" — dropdown picker chiqadi
    if (currentWorkspaceId === 'all') {
        renderCreateWorkspacePicker();
        // Override tanlanmaganda — submit disabled
        if (!_createWsOverride) {
            if (group) group.classList.add('hidden');
            if (list) list.innerHTML = '';
            renderResponsibleSection();
            if (submitBtn) submitBtn.disabled = true;
            return;
        }
        if (submitBtn) submitBtn.disabled = false;
        // Override personal yoki kompaniya bo'lishi mumkin — pastdagi mantiq bilan davom
        const eff = _effectiveCreateWs();
        if (eff.id === 'personal') {
            if (group) group.classList.add('hidden');
            renderResponsibleSection();
            return;
        }
        try {
            const data = await apiRequest(`/companies/${eff.id}/members`);
            companyMembers = data.members || [];
            const self = companyMembers.find(m => m.is_self);
            if (self) selectedAssigneeIds.push(self.id);
            renderAssignees();
            if (group) group.classList.remove('hidden');
            renderResponsibleSection();
            if (hint) hint.textContent = `${companyMembers.length} xodim - Tanlangan: ${selectedAssigneeIds.length}`;
        } catch (e) {
            if (group) group.classList.add('hidden');
            if (list) list.innerHTML = '';
            console.error('Members load error:', e);
        }
        return;
    }

    // Standart oqim — workspace switcher orqali tanlangan
    _createWsOverride = null;
    if (label) {
        label.textContent = currentWorkspaceName;
        label.classList.remove('ws-needs-pick');
        label.onclick = null;
        label.style.cursor = '';
    }
    if (submitBtn) submitBtn.disabled = false;

    if (currentWorkspaceId === 'personal') {
        group.classList.add('hidden');
        if (list) list.innerHTML = '';
        renderResponsibleSection();
        return;
    }

    try {
        const data = await apiRequest(`/companies/${currentWorkspaceId}/members`);
        companyMembers = data.members || [];
        const self = companyMembers.find(m => m.is_self);
        if (self) selectedAssigneeIds.push(self.id);
        renderAssignees();
        group.classList.remove('hidden');
        renderResponsibleSection();
        if (hint) hint.textContent = `${companyMembers.length} xodim - Tanlangan: ${selectedAssigneeIds.length}`;
    } catch (e) {
        group.classList.add('hidden');
        if (list) list.innerHTML = '';
        console.error('Members load error:', e);
    }
}

function renderAssignees() {
    const list = document.getElementById('assignees-list');
    if (!list) return;

    const totalSelected = selectedAssigneeIds.length + externalAssignees.length;

    // Asosiy guruh a'zolari
    const mainHtml = companyMembers.map(m => {
        const selected = selectedAssigneeIds.includes(m.id);
        const initial = (m.name || '?').charAt(0).toUpperCase();
        const roleBadge = m.role === 'owner' ? IC.crown : (m.role === 'admin' ? IC.shield : IC.user);
        return `
            <div class="assignee-chip ${selected ? 'selected' : ''}" onclick="toggleAssignee(${m.id})">
                <span class="assignee-avatar">${escapeHtml(initial)}</span>
                <span class="assignee-name">${roleBadge} ${escapeHtml(m.name)}${m.is_self ? ' (siz)' : ''}</span>
                <span class="assignee-check">${selected ? '✓' : ''}</span>
            </div>`;
    }).join('');

    // Tashqi guruhdan qo'shilganlar
    const extHtml = externalAssignees.length ? `
        <div class="assignee-ext-header">${IC.plus} Boshqa guruhdan qo'shilganlar</div>
        ${externalAssignees.map(m => `
            <div class="assignee-chip selected ext-member">
                <span class="assignee-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</span>
                <span class="assignee-name">${IC.user} ${escapeHtml(m.name)} <span class="ext-group-tag">${escapeHtml(m.group_name)}</span></span>
                <span class="assignee-check remove-ext" onclick="event.stopPropagation();removeExternalAssignee(${m.id})">✕</span>
            </div>`).join('')}
    ` : '';

    // "Boshqa guruhdan qo'shish" tugmasi
    const addBtn = `
        <button class="assignee-add-group-btn" onclick="openGroupPickerSheet()">
            ${IC.plus} Boshqa guruhdan qo'shish
        </button>`;

    list.innerHTML = mainHtml + extHtml + addBtn;
}

function toggleAssignee(uid) {
    const idx = selectedAssigneeIds.indexOf(uid);
    if (idx >= 0) selectedAssigneeIds.splice(idx, 1);
    else selectedAssigneeIds.push(uid);
    renderAssignees();
    renderResponsibleSection();
    const totalSel = selectedAssigneeIds.length + externalAssignees.length;
    const hint = document.getElementById('assignees-hint');
    if (hint) hint.textContent = `${companyMembers.length} xodim - Tanlangan: ${totalSel}`;
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function removeExternalAssignee(uid) {
    externalAssignees = externalAssignees.filter(m => m.id !== uid);
    selectedResponsibleIds = selectedResponsibleIds.filter(id => id !== uid);
    renderAssignees();
    renderResponsibleSection();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

// ===== Mas'ul shaxs (Responsible) =====
function renderResponsibleSection() {
    const sec = document.getElementById('responsible-group');
    if (!sec) return;
    const allSel = getAllSelectedAssignees();
    const hasMembers = companyMembers.length > 0 || allSel.length > 0;
    if (!hasMembers) {
        sec.classList.add('hidden');
        return;
    }
    sec.classList.remove('hidden');
    const respChips = selectedResponsibleIds
        .map(id => {
            const m = companyMembers.find(x => x.id === id) || allSel.find(x => x.id === id);
            return m ? `<span class="resp-chip">⭐ ${escapeHtml(m.name)} <button class="resp-clear-btn" onclick="toggleResponsibleUser(${id})">✕</button></span>` : '';
        })
        .filter(Boolean)
        .join('');
    const respDisplay = document.getElementById('resp-display');
    if (respDisplay) respDisplay.innerHTML =
        respChips
        + `<button class="resp-pick-btn" onclick="openResponsibleSheet()">${IC.plus} Mas'ul qo'shish</button>`;
}

function getAllSelectedAssignees() {
    const fromMain = companyMembers.filter(m => selectedAssigneeIds.includes(m.id));
    return [...fromMain, ...externalAssignees];
}

function clearResponsible() {
    selectedResponsibleIds = [];
    renderResponsibleSection();
}

function openResponsibleSheet() {
    const sheet = document.getElementById('resp-sheet');
    const list = document.getElementById('resp-sheet-list');
    // Show ALL company members
    const allMembers = companyMembers.length > 0 ? companyMembers : getAllSelectedAssignees();
    if (allMembers.length === 0) return;
    list.innerHTML = allMembers.map(m => {
        const isResp = selectedResponsibleIds.includes(m.id);
        return `
        <div class="gp-member-row ${isResp ? 'selected' : ''}" onclick="toggleResponsibleUser(${m.id})">
            <span class="gp-member-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</span>
            <span class="gp-member-name">${escapeHtml(m.name)}${m.is_self ? ' (siz)' : ''}</span>
            ${isResp ? '<span class="gp-check">⭐</span>' : ''}
        </div>`;
    }).join('');
    sheet.classList.remove('hidden');
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function toggleResponsibleUser(uid) {
    if (selectedResponsibleIds.includes(uid)) {
        selectedResponsibleIds = selectedResponsibleIds.filter(id => id !== uid);
    } else {
        selectedResponsibleIds.push(uid);
    }
    // Update sheet list in-place if open
    const sheet = document.getElementById('resp-sheet');
    if (sheet && !sheet.classList.contains('hidden')) {
        openResponsibleSheet(); // re-render
    }
    renderResponsibleSection();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function setResponsibleUser(uid) {
    toggleResponsibleUser(uid);
}

// ===== Boshqa guruhdan qo'shish =====
let _gmCurrentGroupName = '';
let _gmCurrentGroupId = null;

async function openGroupPickerSheet() {
    const sheet = document.getElementById('group-picker-sheet');
    const list = document.getElementById('group-picker-list');
    sheet.classList.remove('hidden');
    list.innerHTML = '<div class="gp-loading">⏳ Guruhlar yuklanmoqda...</div>';
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        // Load all workspaces (cache them)
        if (!_allWorkspaces.length) {
            const data = await apiRequest('/workspaces');
            _allWorkspaces = (data.workspaces || []).filter(w => w.id !== 'personal' && w.id !== 'all');
        }
        const others = _allWorkspaces.filter(w => String(w.id) !== String(currentWorkspaceId));
        if (others.length === 0) {
            list.innerHTML = `
                <div class="gp-empty">Boshqa guruhlar yo'q</div>
                <button class="gp-invite-btn" id="gp-invite-btn-empty">📨 Taklif havolasi yuborish</button>`;
            document.getElementById('gp-invite-btn-empty')?.addEventListener('click', openInviteSheet);
            return;
        }
        // Build with data attributes (no inline onclick = no escape issues)
        list.innerHTML = others.map(w => `
            <div class="gp-group-row" data-gid="${w.id}">
                <span class="gp-group-icon">${IC.building}</span>
                <span class="gp-group-name">${escapeHtml(w.name)}</span>
                <span class="gp-arrow">›</span>
            </div>`).join('') +
            `<div class="gp-divider"></div>
             <button class="gp-invite-btn" id="gp-invite-btn-pick">📨 Taklif havolasi yuborish</button>`;

        // Attach click handlers via JS
        list.querySelectorAll('.gp-group-row').forEach((el, idx) => {
            el.addEventListener('click', () => {
                const gid = el.dataset.gid;
                const w = others.find(x => String(x.id) === String(gid));
                if (w) openGroupMemberSheet(w.id, w.name);
            });
        });
        document.getElementById('gp-invite-btn-pick')?.addEventListener('click', openInviteSheet);
    } catch(e) {
        list.innerHTML = '<div class="gp-empty">Xatolik yuz berdi</div>';
        console.error(e);
    }
}

async function openGroupMemberSheet(groupId, groupName) {
    _gmCurrentGroupId = groupId;
    _gmCurrentGroupName = groupName;
    const sheet = document.getElementById('group-member-sheet');
    const title = document.getElementById('gm-sheet-title');
    const list = document.getElementById('gm-sheet-list');
    if (title) title.innerHTML = IC.building + ' ' + groupName;
    sheet.classList.remove('hidden');
    document.getElementById('group-picker-sheet').classList.add('hidden');
    list.innerHTML = '<div class="gp-loading">⏳ A\'zolar yuklanmoqda...</div>';
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        const data = await apiRequest(`/companies/${groupId}/members`);
        const members = data.members || [];
        const alreadyIds = new Set([...selectedAssigneeIds, ...externalAssignees.map(e => e.id)]);
        if (members.length === 0) {
            list.innerHTML = '<div class="gp-empty">Bu guruhda a\'zolar yo\'q</div>';
            return;
        }
        // data-* attributes — no escape problems
        list.innerHTML = members.map(m => {
            const alreadySel = alreadyIds.has(m.id);
            return `
            <div class="gp-member-row ${alreadySel ? 'already-added' : ''}" data-uid="${m.id}" data-already="${alreadySel ? '1' : '0'}">
                <span class="gp-member-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</span>
                <span class="gp-member-name">${escapeHtml(m.name)}${m.is_self ? ' (siz)' : ''}</span>
                <span class="gp-check">${alreadySel ? '✓' : '+'}</span>
            </div>`;
        }).join('') +
        `<div class="gp-divider"></div>
         <button class="gp-invite-btn" id="gp-invite-btn-mem">📨 Bu guruhda yo'q? Taklif yuboring</button>`;

        // Attach event listeners
        list.querySelectorAll('.gp-member-row').forEach(el => {
            if (el.dataset.already === '1') return;
            el.addEventListener('click', () => {
                const uid = parseInt(el.dataset.uid);
                const m = members.find(x => x.id === uid);
                if (m) addExternalAssignee(m.id, m.name, m.role || 'member', _gmCurrentGroupId, _gmCurrentGroupName);
            });
        });
        document.getElementById('gp-invite-btn-mem')?.addEventListener('click', openInviteSheet);
    } catch(e) {
        list.innerHTML = '<div class="gp-empty">Xatolik yuz berdi</div>';
        console.error(e);
    }
}

function addExternalAssignee(id, name, role, groupId, groupName) {
    if (externalAssignees.some(e => e.id === id)) return;
    externalAssignees.push({ id, name, role, group_id: groupId, group_name: groupName });
    document.getElementById('group-member-sheet')?.classList.add('hidden');
    document.getElementById('group-picker-sheet')?.classList.add('hidden');
    renderAssignees();
    renderResponsibleSection();
    const totalSel = selectedAssigneeIds.length + externalAssignees.length;
    const hint = document.getElementById('assignees-hint');
    if (hint) hint.textContent = `Tanlangan: ${totalSel}`;
    showToast(`✅ ${name} qo'shildi`);
    if (tg) tg.HapticFeedback?.notificationOccurred('success');
}

// ===== Invite sheet =====
async function openInviteSheet() {
    document.getElementById('group-member-sheet')?.classList.add('hidden');
    document.getElementById('group-picker-sheet')?.classList.add('hidden');
    const sheet = document.getElementById('invite-sheet');
    sheet.classList.remove('hidden');
    document.getElementById('invite-link-val').textContent = '⏳ Yuklanmoqda...';
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        const data = await apiRequest('/invite-link');
        const link = data.link || '';
        document.getElementById('invite-link-val').textContent = link;
        document.getElementById('invite-link-val').dataset.link = link;
    } catch(e) {
        document.getElementById('invite-link-val').textContent = 'Xatolik';
    }
}

function copyInviteLink() {
    const el = document.getElementById('invite-link-val');
    const link = el.dataset.link || el.textContent;
    if (!link || link === '⏳ Yuklanmoqda...' || link === 'Xatolik') return;
    navigator.clipboard?.writeText(link).catch(() => {});
    showToast('✅ Havola nusxalandi!');
    if (tg) tg.HapticFeedback?.notificationOccurred('success');
}

function shareInviteLink() {
    const el = document.getElementById('invite-link-val');
    const link = el.dataset.link || el.textContent;
    if (!link || link === '⏳ Yuklanmoqda...' || link === 'Xatolik') return;
    const shareText = encodeURIComponent('Vazifalar botiga qo\'shiling: ');
    const shareLink = encodeURIComponent(link);
    if (tg) {
        tg.openTelegramLink(`https://t.me/share/url?url=${shareLink}&text=${shareText}`);
    } else {
        window.open(`https://t.me/share/url?url=${shareLink}&text=${shareText}`, '_blank');
    }
}

// ===== Custom Deadline Picker =====
const _MONTH_UZ = ['Yanvar','Fevral','Mart','Aprel','May','Iyun','Iyul','Avgust','Sentyabr','Oktyabr','Noyabr','Dekabr'];

// Til bo'yicha oy va kun nomlari
function _monthName(idx) {
    const m = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'][idx];
    const t = tr('app.month.' + m);
    return (t && t !== 'app.month.' + m) ? t : _MONTH_UZ[idx];
}
function _dayShort(idx) {
    // idx: 0=Mon ... 6=Sun
    const d = ['mon','tue','wed','thu','fri','sat','sun'][idx];
    return tr('app.day.' + d) || ['Du','Se','Ch','Pa','Ju','Sh','Ya'][idx];
}
function _dayLong(idx) {
    // idx: 0=Mon ... 6=Sun
    const d = ['mon','tue','wed','thu','fri','sat','sun'][idx];
    const t = tr('app.day_full.' + d);
    return (t && t !== 'app.day_full.' + d) ? t : ['Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba','Yakshanba'][idx];
}
let _dlState = { y: 0, m: 0, d: 0, hour: 14, minute: 0, viewY: 0, viewM: 0 };

function _dlInit() {
    const now = new Date();
    if (!_dlState.y) {
        _dlState.y = now.getFullYear();
        _dlState.m = now.getMonth();
        _dlState.d = now.getDate();
        _dlState.hour = now.getHours();
        _dlState.minute = Math.round(now.getMinutes()/5)*5;
        _dlState.viewY = _dlState.y;
        _dlState.viewM = _dlState.m;
    }
}

function openDeadlinePicker() {
    _dlInit();
    document.getElementById('dl-sheet').classList.remove('hidden');
    _dlRenderCal();
    _dlUpdatePreview();
    _dlRenderTime();
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function _dlRenderCal() {
    const y = _dlState.viewY, m = _dlState.viewM;
    document.getElementById('dl-cal-month').textContent = `${_MONTH_UZ[m]} ${y}`;

    const first = new Date(y, m, 1);
    const startDow = (first.getDay() + 6) % 7;  // Mon=0
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const daysPrev = new Date(y, m, 0).getDate();

    const today = new Date();
    const tY = today.getFullYear(), tM = today.getMonth(), tD = today.getDate();

    let html = '';
    // Prev month tail
    for (let i = startDow - 1; i >= 0; i--) {
        html += `<button class="dl-d dl-d-out" disabled>${daysPrev - i}</button>`;
    }
    // Current month
    for (let d = 1; d <= daysInMonth; d++) {
        const isPast = (y < tY) || (y === tY && m < tM) || (y === tY && m === tM && d < tD);
        const isSelected = (y === _dlState.y && m === _dlState.m && d === _dlState.d);
        const isToday = (y === tY && m === tM && d === tD);
        let cls = 'dl-d';
        if (isPast) cls += ' dl-d-past';
        if (isSelected) cls += ' dl-d-sel';
        if (isToday) cls += ' dl-d-today';
        const dis = isPast ? 'disabled' : '';
        html += `<button class="${cls}" ${dis} onclick="dlSelectDay(${y},${m},${d})">${d}</button>`;
    }
    // Next month head — fill grid
    const total = startDow + daysInMonth;
    const tail = (7 - (total % 7)) % 7;
    for (let i = 1; i <= tail; i++) {
        html += `<button class="dl-d dl-d-out" disabled>${i}</button>`;
    }
    document.getElementById('dl-cal-grid').innerHTML = html;
}

function dlCalNav(delta) {
    let y = _dlState.viewY, m = _dlState.viewM + delta;
    while (m < 0) { m += 12; y--; }
    while (m > 11) { m -= 12; y++; }
    _dlState.viewY = y; _dlState.viewM = m;
    _dlRenderCal();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function dlSelectDay(y, m, d) {
    _dlState.y = y; _dlState.m = m; _dlState.d = d;
    _dlRenderCal();
    _dlUpdatePreview();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function _dlRenderTime() {
    document.getElementById('dl-hour').textContent = String(_dlState.hour).padStart(2,'0');
    document.getElementById('dl-min').textContent  = String(_dlState.minute).padStart(2,'0');
    _dlUpdatePreview();
}

function _dlUpdatePreview() {
    const el = document.getElementById('dl-sel-text');
    if (!el || !_dlState.y) return;
    const pad = n => String(n).padStart(2,'0');
    const mn = Array.from({length:12}, (_,i) => _monthName(i));
    el.textContent = `${_dlState.d} ${mn[_dlState.m]} ${_dlState.y}, soat ${pad(_dlState.hour)}:${pad(_dlState.minute)}`;
}

function dlTimeNudge(field, delta) {
    if (field === 'h') {
        _dlState.hour = (_dlState.hour + delta + 24) % 24;
    } else {
        _dlState.minute = (_dlState.minute + delta + 60) % 60;
    }
    _dlRenderTime();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function dlSetTime(h, m) {
    _dlState.hour = h; _dlState.minute = m;
    _dlRenderTime();
    if (tg) tg.HapticFeedback?.selectionChanged();
}

// Optional one-shot callback — set before opening picker, cleared after use
let _dlOnConfirm = null;

function confirmDeadlinePicker() {
    const dt = new Date(_dlState.y, _dlState.m, _dlState.d, _dlState.hour, _dlState.minute);
    if (dt < new Date()) {
        showToast("⚠️ O'tib ketgan vaqt tanlandi", true);
        return;
    }
    const pad = n => String(n).padStart(2,'0');
    const isoLocal = `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    document.getElementById('dl-sheet').classList.add('hidden');
    if (tg) tg.HapticFeedback?.notificationOccurred('success');

    // If a one-shot callback is registered (e.g. step deadline), use it
    if (typeof _dlOnConfirm === 'function') {
        const cb = _dlOnConfirm;
        _dlOnConfirm = null;
        cb(isoLocal);
        showToast('✅ Deadline belgilandi');
        return;
    }

    // Default: write to main task form
    document.getElementById('task-deadline').value = isoLocal;
    const display = `${pad(dt.getDate())}.${pad(dt.getMonth()+1)}.${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    document.getElementById('dl-picker-text').textContent = '⏰ ' + display;
    document.getElementById('dl-picker-text').classList.add('chosen');
    document.getElementById('dl-picker-clear').classList.remove('hidden');
    showToast('✅ Deadline belgilandi');
}

function clearDeadline() {
    document.getElementById('task-deadline').value = '';
    document.getElementById('dl-picker-text').textContent = 'Sana va vaqt tanlang';
    document.getElementById('dl-picker-text').classList.remove('chosen');
    document.getElementById('dl-picker-clear').classList.add('hidden');
    if (tg) tg.HapticFeedback?.selectionChanged();
}

function setQuickDeadline(kind) {
    const now = new Date();
    let dt;
    if (kind === 'today') {
        dt = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 18, 0);
    } else if (kind === 'tomorrow') {
        dt = new Date(now.getFullYear(), now.getMonth(), now.getDate()+1, 12, 0);
    } else if (kind === 'week') {
        // Next Sunday 18:00
        const d = new Date(now);
        const daysToSun = (7 - d.getDay()) % 7 || 7;
        d.setDate(d.getDate() + daysToSun);
        dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 18, 0);
    }
    _dlState.y = dt.getFullYear();
    _dlState.m = dt.getMonth();
    _dlState.d = dt.getDate();
    _dlState.hour = dt.getHours();
    _dlState.minute = dt.getMinutes();
    _dlState.viewY = _dlState.y;
    _dlState.viewM = _dlState.m;
    confirmDeadlinePicker();
}

// ===== Quick Stats =====
function updateQuickStats(stats) {
    animateNumber('stat-total', stats.total || 0);
    animateNumber('stat-active', (stats.in_progress || 0) + (stats.new || 0));
    animateNumber('stat-done', stats.done || 0);
    animateNumber('stat-overdue', stats.overdue || 0);
    
    const statsEl = document.getElementById('user-stats');
    if (statsEl) {
        const total = stats.total || 0;
        const rate = stats.completion_rate || 0;
        const lbl = (tr('app.stats.summary') !== 'app.stats.summary')
            ? tr('app.stats.summary').replace('{total}', total).replace('{rate}', rate)
            : `${total} ${tr('app.stats.tasks_word') || 'vazifa'} — ${rate}% ${tr('app.stats.done_word') || 'bajarildi'}`;
        statsEl.textContent = lbl;
    }
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
let _statsMemberId = null;   // CEO filter: tanlangan a'zo ID
let _statsLastData = null;   // oxirgi stats ma'lumotlari (member list uchun)

function updateStatsTab(stats) {
    _statsLastData = stats;

    // CEO member filter panel
    _renderStatsMemberFilter(stats);

    // Title: agar member filter qo'llanilgan bo'lsa
    const titleEl = document.getElementById('stats-tab-title');
    if (titleEl) {
        if (stats.member_name) {
            titleEl.innerHTML = `${IC.chart} ${stats.member_name}`;
        } else {
            titleEl.innerHTML = IC.chart + ' Statistikangiz';
        }
    }

    // Joriy oy nomi
    const _monthNames = Array.from({length:12}, (_,i) => _monthName(i));
    const _now = new Date();
    const _monthLabel = `${_monthNames[_now.getMonth()]} ${_now.getFullYear()}`;
    const periodEl = document.querySelector('.stats-period');
    if (periodEl) periodEl.textContent = _monthLabel;

    const _se = id => document.getElementById(id);
    if (_se('stats-total'))       _se('stats-total').textContent       = stats.total || 0;
    if (_se('stats-done-count'))  _se('stats-done-count').textContent  = stats.done || 0;
    if (_se('stats-progress'))    _se('stats-progress').textContent    = stats.in_progress || 0;
    if (_se('stats-overdue-count')) _se('stats-overdue-count').textContent = stats.overdue || 0;

    // Progress circle
    const rate = stats.completion_rate || 0;
    if (_se('completion-rate')) _se('completion-rate').textContent = rate;
    const circle = document.getElementById('progress-circle');
    if (circle) {
        const circumference = 2 * Math.PI * 52;
        const offset = circumference - (rate / 100) * circumference;
        setTimeout(() => { circle.style.strokeDashoffset = offset; }, 300);
    }

    renderStatusChart(stats);
    renderPriorityChart(stats);
    renderTrendChart(stats);
    renderOverdueChart(stats);
    renderMembersChart(stats);

    // Tezlik reytingi — faqat kompaniya workspace uchun
    const _isCompanyWs = currentWorkspaceId && currentWorkspaceId !== 'personal' && currentWorkspaceId !== 'all';
    if (_isCompanyWs) {
        loadSpeedRating(currentWorkspaceId);
    } else {
        const existingRating = document.getElementById('speed-rating-section');
        if (existingRating) existingRating.remove();
    }
}

const _ROLE_META = {
    owner:  { icon: IC.crown,  label: 'Owner',  cls: 'smf-role-owner'  },
    admin:  { icon: IC.star,   label: 'Admin',  cls: 'smf-role-admin'  },
    member: { icon: IC.user,   label: 'Member', cls: 'smf-role-member' },
};

function _renderStatsMemberFilter(stats) {
    let panel = document.getElementById('stats-member-filter-panel');
    if (!stats.is_admin || !Array.isArray(stats.employee_stats) || stats.employee_stats.length === 0) {
        if (panel) panel.remove();
        return;
    }
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'stats-member-filter-panel';
        panel.className = 'smf-panel';
        const statsSection = document.querySelector('#tab-stats .stats-tab-content');
        const progressSec  = document.querySelector('#tab-stats .progress-section');
        if (progressSec) progressSec.after(panel);
        else {
            const statsGrid = document.querySelector('#tab-stats .stats-grid');
            if (statsGrid) statsGrid.parentNode.insertBefore(panel, statsGrid);
            else document.getElementById('tab-stats')?.prepend(panel);
        }
    }

    // "Hammasi" chip
    const allActive = !_statsMemberId;
    let chipsHtml = `
        <button class="smf-chip ${allActive ? 'smf-chip-active' : ''}"
                onclick="filterStatsByMember('')">
            <span class="smf-chip-icon">🌍</span>
            <span class="smf-chip-name">Hammasi</span>
        </button>
    `;

    // Har bir a'zo uchun chip
    stats.employee_stats.forEach(e => {
        const role = e.role || 'member';
        const rm = _ROLE_META[role] || _ROLE_META.member;
        const isActive = _statsMemberId == e.id;
        const total = e.total || 0;
        const done  = e.done  || 0;
        const pct   = total ? Math.round(done / total * 100) : 0;

        chipsHtml += `
            <button class="smf-chip ${isActive ? 'smf-chip-active' : ''} ${rm.cls}"
                    onclick="filterStatsByMember(${e.id})">
                <div class="smf-chip-top">
                    <span class="smf-chip-role-icon">${rm.icon}</span>
                    <span class="smf-chip-name">${escapeHtml((e.name||'').split(' ')[0])}</span>
                </div>
                <div class="smf-chip-stats">
                    <span class="smf-chip-pct">${pct}%</span>
                    <span class="smf-chip-sub">${done}/${total}</span>
                </div>
            </button>
        `;
    });

    // Tanlangan a'zo nomi ko'rsatiladigan sarlavha
    let selectedLabel = '';
    if (_statsMemberId) {
        const sel = stats.employee_stats.find(e => e.id == _statsMemberId);
        if (sel) {
            const rm = _ROLE_META[sel.role] || _ROLE_META.member;
            selectedLabel = `
                <div class="smf-selected-label">
                    ${rm.icon} <b>${escapeHtml(sel.name)}</b>
                    <span class="smf-role-badge ${rm.cls}">${rm.label}</span>
                    <button class="smf-deselect" onclick="filterStatsByMember('')">✕ Tozalash</button>
                </div>
            `;
        }
    }

    panel.innerHTML = `
        <div class="smf-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
            Jamoa a'zolari bo'yicha
        </div>
        <div class="smf-chips-row">${chipsHtml}</div>
        ${selectedLabel}
    `;
}

async function filterStatsByMember(memberId) {
    _statsMemberId = memberId ? parseInt(memberId) : null;
    const ws = currentWorkspaceId;
    let url = `${API_BASE}/stats?company_id=${ws}`;
    if (_statsMemberId) url += `&member_id=${_statsMemberId}`;
    try {
        const headers = {};
        applyAuthHeaders(headers);
        const res = await fetch(url, { headers });
        if (!res.ok) return;
        const stats = await res.json();
        // employee_stats ni saqlab qolish (member filterlashda yo'qolmasin)
        if (_statsLastData && _statsLastData.employee_stats && !stats.employee_stats?.length) {
            stats.employee_stats = _statsLastData.employee_stats;
            stats.is_admin = _statsLastData.is_admin;
        }
        updateStatsTab(stats);
    } catch (e) { console.warn('filterStats error', e); }
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
    const canvas  = document.getElementById('members-chart');
    if (!section || !canvas || typeof Chart === 'undefined') return;

    const hasData = stats.is_admin && Array.isArray(stats.employee_stats) && stats.employee_stats.length > 0;
    if (!hasData) {
        section.classList.add('hidden');
        if (membersChart) { membersChart.destroy(); membersChart = null; }
        return;
    }
    section.classList.remove('hidden');

    // Har bir a'zo uchun ism + rol belgisi
    const labels = stats.employee_stats.map(e => {
        const roleMark = e.role === 'owner' ? ' ★' : e.role === 'admin' ? ' ◆' : '';
        return (e.name || '').split(' ')[0] + roleMark;
    });

    // 4 xil status
    const newTasks   = stats.employee_stats.map(e => e.new        || 0);
    const inProgress = stats.employee_stats.map(e => (e.in_progress || 0) + (e.review || 0));
    const done       = stats.employee_stats.map(e => e.done       || 0);
    const overdue    = stats.employee_stats.map(e => e.overdue    || 0);

    // Vertikal chart uchun balandlik
    const barH = Math.max(260, labels.length * 80 + 60);
    canvas.parentElement.style.height = barH + 'px';

    if (membersChart) membersChart.destroy();

    const datalabelsPlugin = window.ChartDataLabels;

    membersChart = new Chart(canvas, {
        type: 'bar',
        plugins: datalabelsPlugin ? [datalabelsPlugin] : [],
        data: {
            labels,
            datasets: [
                {
                    label: 'Boshlanmagan',
                    data: newTasks,
                    backgroundColor: 'rgba(239,68,68,0.82)',
                    borderColor: '#EF4444',
                    borderWidth: 1.5,
                    borderRadius: { topLeft: 0, topRight: 0, bottomLeft: 6, bottomRight: 6 },
                    borderSkipped: 'bottom',
                    stack: 'tasks',
                },
                {
                    label: 'Jarayonda',
                    data: inProgress,
                    backgroundColor: 'rgba(234,179,8,0.85)',
                    borderColor: '#EAB308',
                    borderWidth: 1.5,
                    borderRadius: 0,
                    borderSkipped: false,
                    stack: 'tasks',
                },
                {
                    label: 'Bajarildi',
                    data: done,
                    backgroundColor: 'rgba(34,197,94,0.85)',
                    borderColor: '#22C55E',
                    borderWidth: 1.5,
                    borderRadius: 0,
                    borderSkipped: false,
                    stack: 'tasks',
                },
                {
                    label: 'Kechikdi',
                    data: overdue,
                    backgroundColor: 'rgba(249,115,22,0.9)',
                    borderColor: '#F97316',
                    borderWidth: 1.5,
                    borderRadius: { topLeft: 6, topRight: 6, bottomLeft: 0, bottomRight: 0 },
                    borderSkipped: 'top',
                    stack: 'tasks',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            // indexAxis: 'x'  → vertikal (pastdan tepaga)
            scales: {
                x: {
                    stacked: true,
                    ticks: {
                        color: 'rgba(255,255,255,0.9)',
                        font: { weight: '700', size: 12 },
                    },
                    grid: { display: false },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255,255,255,0.6)',
                        stepSize: 1, precision: 0,
                    },
                    grid: { color: 'rgba(255,255,255,0.06)' },
                    title: {
                        display: true, text: 'Vazifalar soni',
                        color: 'rgba(255,255,255,0.4)', font: { size: 11 },
                    },
                },
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: 'rgba(255,255,255,0.88)',
                        font: { size: 11 },
                        boxWidth: 12, padding: 10,
                    },
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: (items) => {
                            const idx = items[0]?.dataIndex;
                            const emp = stats.employee_stats[idx];
                            if (!emp) return '';
                            const roleTxt = emp.role === 'owner' ? 'Owner' :
                                            emp.role === 'admin' ? 'Admin' : 'Member';
                            return `${emp.name}  ${roleTxt}`;
                        },
                        footer: (items) => {
                            const idx = items[0]?.dataIndex;
                            const emp = stats.employee_stats[idx];
                            if (!emp) return '';
                            const total = (emp.new||0)+(emp.in_progress||0)+(emp.review||0)+(emp.done||0)+(emp.overdue||0);
                            const pct   = total ? Math.round((emp.done||0)/total*100) : 0;
                            return [`Jami: ${total} ta  ·  Bajarildi: ${pct}%`];
                        },
                    },
                },
                datalabels: datalabelsPlugin ? {
                    display: (ctx) => ctx.dataset.data[ctx.dataIndex] > 0,
                    anchor: 'center',
                    align: 'center',
                    formatter: (val) => val > 0 ? val : '',
                    color: '#fff',
                    font: { weight: 'bold', size: 11 },
                    textShadowColor: 'rgba(0,0,0,0.4)',
                    textShadowBlur: 3,
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
            labels: ['Juda muhum', 'Muhum', "O'rta", 'Past'],
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

    // Joriy oy dinamikasi (1-sanadan bugungi kungacha)
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const daysInMonthSoFar = today.getDate();
    const _monthNamesT = Array.from({length:12}, (_,i) => _monthName(i));
    const _mLabelT = `${_monthNamesT[month]} ${year}`;
    const titleEl = section.querySelector('.chart-title');
    if (titleEl) titleEl.textContent = `📈 ${tr('app.stats.completion_trend')||'Bajarilish trendi'} (${_mLabelT})`;

    const data = [];
    for (let dayNum = 1; dayNum <= daysInMonthSoFar; dayNum++) {
        const d = new Date(year, month, dayNum);
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
            date: String(dayNum).padStart(2,'0') + '.' + String(month+1).padStart(2,'0'),
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
                label: (tr('app.stats.done')||'Bajarilgan'),
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

    // Joriy oy kechikkan vazifalar dinamikasi
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth();
    const daysInMonthSoFarO = today.getDate();

    const data = [];
    for (let dayNum = 1; dayNum <= daysInMonthSoFarO; dayNum++) {
        const d = new Date(year, month, dayNum);
        // Set to end of that day
        const dEnd = new Date(year, month, dayNum, 23, 59, 59);

        let overdue = 0;
        allTasks.forEach(t => {
            if (!t.deadline) return;
            const dl = new Date(t.deadline);
            if (dl > dEnd) return;  // deadline hali kelmagan
            if (t.status === 'cancelled') return;
            // O'sha kunda vazifa bajarilmagan bo'lsa — kechikkan
            // (bajarilgan, lekin deadline'dan keyin yopilgan — kechikib bajarilgan)
            if (t.status !== 'done') {
                overdue++;
                return;
            }
            // status === 'done': kechikib bajarilgan bo'lsa, completed_at vaqtigacha kechikkan edi
            if (t.completed_at && new Date(t.completed_at) > dl) {
                overdue++;
            }
        });

        data.push({
            date: String(dayNum).padStart(2,'0') + '.' + String(month+1).padStart(2,'0'),
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

// ===== Tezlik Reytingi =====
let _speedRatingChart = null;

async function loadSpeedRating(companyId) {
    // Mavjud bo'lsa qayta ishlatamiz
    let section = document.getElementById('speed-rating-section');
    const statsContainer = document.querySelector('#tab-stats .stats-container');
    if (!section && statsContainer) {
        section = document.createElement('div');
        section.id = 'speed-rating-section';
        section.className = 'chart-section';
        statsContainer.appendChild(section);
    }
    if (!section) return;

    section.innerHTML = `
        <h3 class="chart-title">${IC.bolt} Tezlik Reytingi</h3>
        <div class="sr-loading">Yuklanmoqda...</div>
    `;

    try {
        const data = await apiRequest(`/companies/${companyId}/speed_rating`);
        const members = data.members || [];

        if (members.length === 0) {
            section.innerHTML = `
                <h3 class="chart-title">${IC.bolt} Tezlik Reytingi</h3>
                <div class="sr-empty">Hali bajarilgan vazifalar yo'q</div>
            `;
            return;
        }

        // Karta formati
        let cardsHtml = '';
        members.forEach(m => {
            const medal = m.medal || '';
            const rank = m.rank;
            const rankClass = rank === 1 ? 'sr-rank-1' : rank === 2 ? 'sr-rank-2' : rank === 3 ? 'sr-rank-3' : '';
            const timedHtml = m.timed_tasks > 0
                ? `<span class="sr-avg">${m.avg_label}</span><span class="sr-avg-lab"> / vazifa</span>`
                : `<span class="sr-no-time">vaqt kuzatuvi yo'q</span>`;
            const onTimeHtml = m.on_time_rate !== null
                ? `<span class="sr-ontime ${m.on_time_rate >= 80 ? 'sr-ontime-good' : m.on_time_rate >= 50 ? 'sr-ontime-ok' : 'sr-ontime-bad'}">${m.on_time_rate}% vaqtida</span>`
                : '';
            const scoreBar = m.score > 0
                ? `<div class="sr-score-bar"><div class="sr-score-fill" style="width:${Math.min(100, m.score)}%"></div></div>`
                : '';
            cardsHtml += `
                <div class="sr-card ${rankClass}">
                    <div class="sr-card-left">
                        <span class="sr-medal">${medal || rank}</span>
                        <div class="sr-info">
                            <div class="sr-name">${escapeHtml(m.name)}</div>
                            <div class="sr-stats">
                                <span class="sr-done">${m.tasks_done} task</span>
                                ${timedHtml}
                                ${onTimeHtml}
                            </div>
                            ${scoreBar}
                        </div>
                    </div>
                    <div class="sr-score-badge ${rankClass}">${m.score}</div>
                </div>
            `;
        });

        section.innerHTML = `
            <h3 class="chart-title">${IC.bolt} Tezlik Reytingi</h3>
            <p class="sr-desc">Vazifalarni qanchalik tez va o'z vaqtida bajarilishi asosida</p>
            <div class="sr-cards">${cardsHtml}</div>
        `;

    } catch (e) {
        section.innerHTML = `
            <h3 class="chart-title">${IC.bolt} Tezlik Reytingi</h3>
            <div class="sr-empty">Yuklab bo'lmadi</div>
        `;
    }
}

// ===== Tabs =====
let _currentTasksSubtab = 'regular';  // 'regular' | 'workflow'

function initTabs() {
    document.querySelectorAll('.bnav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.bnav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const tabName = btn.dataset.tab;
            const tabId = 'tab-' + tabName;
            document.getElementById(tabId).classList.add('active');

            // Header title ni yangilaymiz
            const tabTitles = { tasks: 'Vazifalar', calendar: 'Kalendar', create: 'Yangi vazifa', kanban: 'Kanban', stats: 'Statistika' };
            const hTitle = document.getElementById('header-title');
            if (hTitle) {
                if (tabName === 'create' && _subtaskParentId) {
                    hTitle.textContent = 'Sub-task yaratish';
                } else {
                    hTitle.textContent = tabTitles[tabName] || 'TaskBot';
                }
            }
            // Tab o'zgarsa nav stack ni tozalaymiz
            _navStack.length = 0;
            document.getElementById('back-btn')?.classList.add('hidden');
            document.getElementById('hamburger-btn')?.classList.remove('hidden');

            // Quick-stats faqat Tasks tabida ko'rinadi
            const qs = document.getElementById('quick-stats');
            if (qs) qs.classList.toggle('hidden', tabName !== 'tasks');

            if (tabName === 'kanban') {
                renderKanbanMemberBar();
                renderKanban();
            }
            if (tabName === 'calendar') {
                renderCalendar();
            }
            // Clear subtask mode when user navigates away from create tab
            if (tabName !== 'create' && _subtaskParentId) {
                _subtaskParentId    = null;
                _subtaskParentTitle = null;
                _updateSubtaskBanner();
            }

            if (tg) tg.HapticFeedback?.impactOccurred('light');
        });
    });

    // Workflow filter chips inside tasks tab
    document.querySelectorAll('.wf-filter-chips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.wf-filter-chips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            _wfFilter = chip.dataset.wfFilter || 'all';
            renderWorkflows();
            if (tg) tg.HapticFeedback?.selectionChanged();
        });
    });
}

function switchTasksSubtab(name) {
    _currentTasksSubtab = name;
    document.querySelectorAll('.tasks-subtab').forEach(b => b.classList.remove('active'));
    document.getElementById('subtab-' + name)?.classList.add('active');

    const panelRegular  = document.getElementById('panel-regular');
    const panelWorkflow = document.getElementById('panel-workflow');

    if (name === 'regular') {
        panelRegular?.classList.remove('hidden');
        panelWorkflow?.classList.add('hidden');
        renderTasks();
    } else {
        panelRegular?.classList.add('hidden');
        panelWorkflow?.classList.remove('hidden');
        loadWorkflows();
    }
    if (tg) tg.HapticFeedback?.selectionChanged();
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
        list.innerHTML = '<div class="wf-empty">📭 Workflow vazifa yo\'q<br><span style="font-size:12px;color:var(--text3)">Bot\'da /newworkflow</span></div>';
        return;
    }

    list.innerHTML = items.map(w => {
        const isDone   = w.status === 'done';
        const statusEm = isDone ? IC.done : w.current_is_me ? IC.play : IC.refresh;
        const statusCls= isDone ? 'wf-s-done' : w.current_is_me ? 'wf-s-me' : 'wf-s-active';
        const statusTxt= isDone ? 'Tugagan' : w.current_is_me ? 'Sizning navbat!' : 'Jarayonda';

        const curStep  = w.steps.find(s => s.status === 'active');
        const curLine  = curStep
            ? `<div class="wf-cur-step">${IC.play} ${escapeHtml(curStep.title)} — <b>${escapeHtml(curStep.assignee_name)}</b>${curStep.deadline ? ' '+IC.clock+curStep.deadline : ''}</div>`
            : (isDone ? '' : '<div class="wf-cur-step" style="color:var(--text3)">'+(tr('app.waiting')||'Kutilmoqda')+'...</div>');

        return `
        <div class="wf-card wf-card-compact" onclick="openWorkflowDetail(${w.task_id})">
            <div class="wf-card-top">
                <div class="wf-card-info">
                    <div class="wf-card-title">#${w.task_id} ${escapeHtml(w.title)}</div>
                    <span class="wf-status-badge ${statusCls}">${statusEm} ${statusTxt}</span>
                </div>
                <div class="wf-progress-wrap">
                    <div class="wf-progress-text">${w.done_steps}/${w.total_steps}</div>
                    <div class="wf-progress-bar"><div class="wf-progress-fill" style="width:${w.progress_percent}%"></div></div>
                </div>
            </div>
            ${curLine}
            <div class="wf-card-footer">${IC.calendar} ${w.created_at} &nbsp;•&nbsp; ${IC.step} ${w.total_steps} qadam</div>
        </div>`;
    }).join('');
}

// Workflow detail — xuddi oddiy task modal kabi (bottom-sheet)
function openWorkflowDetail(taskId) {
    const w = _wfData.find(x => x.task_id === taskId);
    if (!w) return;
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    const isDone = w.status === 'done';
    const typeEm = {photo:'🖼', video:'🎥', document:'📄', audio:'🎵', voice:'🎙'};

    // ---- Progress bar ----
    const pct = w.progress_percent || 0;
    const progressBar = `
        <div style="margin:4px 0 12px">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text3);margin-bottom:4px">
                <span>${IC.step} Qadamlar: ${w.done_steps}/${w.total_steps}</span>
                <span>${pct}%</span>
            </div>
            <div style="height:6px;border-radius:3px;background:var(--border);overflow:hidden">
                <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:3px;transition:width .3s"></div>
            </div>
        </div>`;

    // ---- Overview rows (like modal-section) ----
    const statusTxt = isDone ? IC.done+' Tugagan' : IC.refresh+' Jarayonda';
    let bodyHtml = `
        <div class="modal-section">
            <div class="modal-detail">
                <div class="modal-detail-label">${IC.pin} Holat</div>
                <div class="modal-detail-value">${statusTxt}</div>
            </div>
            <div class="modal-detail">
                <div class="modal-detail-label">${IC.calendar} Yaratildi</div>
                <div class="modal-detail-value">${w.created_at}</div>
            </div>
        </div>
        ${w.description ? `<div class="modal-detail"><div class="modal-detail-label">Tavsif</div><div class="modal-detail-value">${escapeHtml(w.description)}</div></div>` : ''}
        ${progressBar}
        <div class="modal-detail-label" style="margin-bottom:8px">${IC.step} QADAMLAR</div>
    `;

    // ---- User flags (workflow ichida ishtirok etayotgan odam comment va fayl yuklay oladi) ----
    const isCreator = (w.creator_id === window._myUserId);
    const isOtherStepOwner = w.steps.some(st => st.is_me);

    // ---- Steps ----
    w.steps.forEach(s => {
        const icon = s.status === 'done' ? IC.done : s.status === 'active' ? IC.play : s.status === 'blocked' ? IC.pause : IC.circle;
        const isCur = s.status === 'active';
        const cardStyle = isCur
            ? 'background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.35);border-radius:14px;padding:12px 14px;margin-bottom:10px'
            : 'background:var(--glass);border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-bottom:10px;opacity:' + (s.status==='done'?'0.75':'1');

        let meta = [];
        if (s.started_at)   meta.push(`${IC.play} ${s.started_at}`);
        if (s.completed_at) meta.push(`${IC.done} ${s.completed_at}`);
        if (s.deadline)     meta.push(`${IC.clock} ${s.deadline}`);
        // Nisbiy muddat — navbati kelmagan qadamlarda taxminiy sana bilan
        if (s.duration_days && s.status === 'pending' && !s.deadline) {
            meta.push(s.projected_deadline
                ? `⏳ ${s.duration_days} kun · ≈ ${s.projected_deadline} (taxminiy)`
                : `⏳ ${s.duration_days} kun (navbat kelganda)`);
        }
        const metaHtml = meta.length ? `<div style="font-size:11px;color:var(--text3);margin-top:5px;display:flex;gap:10px;flex-wrap:wrap">${meta.map(m=>`<span>${m}</span>`).join('')}</div>` : '';

        // Faqat qadam eslatmasi (note) — izohlar pastda commsHtml da ko'rsatiladi (takror bo'lmasin)
        let noteHtml = '';
        if (s.note) {
            noteHtml = `<div style="font-size:12px;background:var(--glass2);padding:6px 10px;border-radius:8px;margin-top:5px;color:var(--text2)">${IC.comment} ${escapeHtml(s.note)}</div>`;
        }

        let attsHtml = '';
        if (s.attachments && s.attachments.length) {
            attsHtml = `<div class="wfs-atts">${s.attachments.map(a => {
                const em = typeEm[a.file_type] || IC.attach;
                const fname = escapeHtml(a.file_name || a.file_type || 'fayl');
                const uploader = escapeHtml(a.user_name || '');
                if (a.file_url) {
                    if (a.file_type === 'photo') {
                        return `<a href="${a.file_url}" target="_blank" class="wfs-att-img"><img src="${a.file_url}" alt=""><span>${uploader}</span></a>`;
                    }
                    if (a.file_type === 'video') {
                        return `<video class="wfs-att-video" src="${a.file_url}" controls preload="metadata"></video>`;
                    }
                    if (a.file_type === 'voice' || a.file_type === 'audio') {
                        return `<div class="wfs-att-audio"><audio src="${a.file_url}" controls preload="none"></audio><div class="wfs-att-by">${em} ${uploader}</div></div>`;
                    }
                    return `<a href="${a.file_url}" target="_blank" class="wfs-att-file">${em} <span>${fname}</span><small>${uploader}</small></a>`;
                }
                return `<span class="wfs-att-file" title="bot orqali">${em} ${fname}<small>${uploader}</small></span>`;
            }).join('')}</div>`;
        }

        // Izohlar — konteyner har doim mavjud (id bilan) — optimistik qo'shish uchun
        const _cName = (c) => (typeof c.user === 'string' ? c.user : (c.user && c.user.name)) || c.user_name || '?';
        const commsInner = (s.comments && s.comments.length)
            ? s.comments.map(c =>
                `<div class="wfs-comment"><b>${escapeHtml(_cName(c))}</b> <span>${escapeHtml(c.created_at || '')}</span><div>${escapeHtml(c.content)}</div></div>`
              ).join('')
            : '';
        const commsHtml = `<div class="wfs-comments" id="wfs-comments-${s.id}"${commsInner ? '' : ' style="display:none"'}>${commsInner}</div>`;

        const meBtnHtml = s.is_me && (s.status === 'active' || s.status === 'pending') && !isDone
            ? `<button class="modal-action-btn btn-primary" style="margin-top:8px" onclick="handleStepAction(${w.task_id},'${s.status}');closeWfDetailModal()">
                ${s.status==='pending'?IC.play+' Boshlash':IC.done+' Tugatish'}
               </button>` : '';

        // Comment + Upload form — agar qatnashuvchi bo'lsa
        // (mas'ul yoki yaratuvchi yoki boshqa qadam egasi)
        const canInteract = s.is_me || isCreator || isOtherStepOwner;
        const interactHtml = canInteract ? `
            <div class="wfs-form">
                <textarea class="wfs-cm-input" id="wfs-cm-${s.id}" rows="2" placeholder="${tr('app.wf.comment_ph') || "Izoh yozing..."}"></textarea>
                <div class="wfs-form-row">
                    <label class="wfs-upload-btn">
                        ${IC.attach}
                        <input type="file" style="display:none" onchange="wfStepUpload(${s.id}, this, ${w.task_id})">
                    </label>
                    <button class="wfs-cm-send" onclick="wfStepComment(${s.id}, ${w.task_id})">${IC.send || '📨'}</button>
                </div>
            </div>` : '';

        bodyHtml += `
            <div style="${cardStyle}">
                <div style="display:flex;gap:10px;align-items:flex-start">
                    <div style="font-size:20px;line-height:1;margin-top:1px">${icon}</div>
                    <div style="flex:1;min-width:0">
                        <div style="font-size:14px;font-weight:700;color:var(--text)">${s.order}. ${escapeHtml(s.title)}</div>
                        <div style="font-size:12px;color:var(--text2);margin-top:2px">
                            ${IC.user} ${escapeHtml(s.assignee_name)}${s.is_me ? ' <b style="color:var(--accent)">(siz)</b>' : ''}
                        </div>
                        ${metaHtml}${noteHtml}${attsHtml}${commsHtml}${meBtnHtml}${interactHtml}
                    </div>
                </div>
            </div>`;
    });

    // Mind map uchun — workflow ma'lumotini saqlaymiz (step izoh/fayl bilan)
    window._currentTaskFull = {
        id: w.task_id,
        title: w.title,
        status: w.status,
        priority: w.priority || 'medium',
        deadline: w.deadline || null,
        completed_at: w.completed_at || null,
        creator_name: w.creator_name || null,
        has_workflow: true,
        history: [],
        attachments: [],
        assignees: w.assignees || [],
        subtasks: [],
        wfSteps: w.steps || [],   // to'liq step ma'lumoti (izoh matni + fayl URL)
    };
    currentTaskId = w.task_id;

    // Use the existing task modal — just fill it
    document.getElementById('modal-title').textContent = `#${w.task_id} ${w.title}`;
    document.getElementById('modal-body').innerHTML = bodyHtml;
    document.getElementById('modal-actions').innerHTML = '';
    document.getElementById('task-modal').classList.remove('hidden');
    document.getElementById('task-modal').dataset.wfMode = '1';
}

function closeWfDetailModal() {
    closeModal();
}

// Workflow qadami uchun izoh yuborish
async function wfStepComment(stepId, taskId) {
    const ta = document.getElementById('wfs-cm-' + stepId);
    if (!ta) return;
    const content = (ta.value || '').trim();
    if (content.length < 1) return;

    // Darhol tozalab, izohni ko'rsatamiz (optimistik) — modal qayta yuklanmaydi
    ta.value = '';
    ta.style.height = 'auto';
    const name = window._currentUserName || 'Siz';
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const dstr = `${pad(d.getDate())}.${pad(d.getMonth()+1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;

    const cont = document.getElementById('wfs-comments-' + stepId);
    let node = null;
    if (cont) {
        cont.style.display = '';
        node = document.createElement('div');
        node.className = 'wfs-comment';
        node.style.opacity = '0.55';
        node.innerHTML = `<b>${escapeHtml(name)}</b> <span>${dstr}</span><div>${escapeHtml(content)}</div>`;
        cont.appendChild(node);
        node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    if (tg) tg.HapticFeedback?.notificationOccurred('success');
    if (typeof FX !== 'undefined' && FX.play) FX.play('send');

    // Mind map cache'ini ham yangilaymiz
    try {
        const wf = window._currentTaskFull;
        if (wf && Array.isArray(wf.wfSteps)) {
            const st = wf.wfSteps.find(x => x.id === stepId);
            if (st) { (st.comments = st.comments || []).push({ user_name: name, content, created_at: dstr }); }
        }
    } catch {}

    try {
        await apiRequest(`/workflows/steps/${stepId}/comment`, 'POST', { content });
        if (node) node.style.opacity = '1';   // tasdiqlandi
    } catch (e) {
        if (node) { node.style.opacity = '1'; node.style.borderLeft = '2px solid #ef4444'; node.title = 'Yuborilmadi'; }
        if (typeof showToast === 'function') showToast('❌ ' + (e.message || e));
    }
}

// Workflow qadami uchun fayl yuklash
async function wfStepUpload(stepId, inputEl, taskId) {
    const file = inputEl.files && inputEl.files[0];
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) {
        if (typeof showToast === 'function') showToast('❌ Fayl 100 MB dan katta');
        return;
    }
    const fd = new FormData();
    fd.append('file', file);
    try {
        const headers = {};
        applyAuthHeaders(headers);
        if (typeof showToast === 'function') showToast('⏳ Yuklanmoqda...');
        const res = await fetch(API_BASE + `/workflows/steps/${stepId}/upload`, {
            method: 'POST', headers, body: fd,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Yuklash xatosi');
        if (typeof showToast === 'function') showToast('✅ Fayl yuklandi');
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        inputEl.value = '';
        openWorkflowDetail(taskId); // qayta yuklab modal yangilanadi
    } catch (e) {
        if (typeof showToast === 'function') showToast('❌ ' + (e.message || e));
    }
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
                <h3>${IC.step} Qadamni tugatish</h3>
                <button class="wf-modal-close" onclick="closeStepCompleteModal()">×</button>
            </div>
            <div class="wf-modal-body">
                <label class="wf-lbl">${IC.comment} Nimani bajardingiz? (ixtiyoriy)</label>
                <textarea id="wf-comment-input" class="wf-textarea" rows="3"
                          placeholder="Qisqacha yozing..."></textarea>
            </div>
            <div class="wf-modal-foot">
                <button class="wf-btn-secondary" onclick="closeStepCompleteModal()">Bekor</button>
                <button class="wf-btn-primary" onclick="submitStepComplete(${taskId})">${IC.done} Saqlash</button>
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
    // Faqat oddiy vazifalar filterlari — wf filterlari alohida initTabs da
    document.querySelectorAll('.filter-chips .chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentFilter = chip.dataset.filter || 'active';
            renderTasks();
            FX.select();
        });
    });
}

// ===== Render Tasks =====
// Status labels — resolved at runtime via i18n so they appear in user's language
function getStatusLabel(status) {
    const key = 'app.status.' + status;
    const translated = tr(key);
    // If key not in dict, fall back to built-in Uzbek defaults
    if (translated === key) {
        const FB = { new:'Yangi', in_progress:'Jarayonda', review:"Ko'rilmoqda",
                     done:'Bajarildi', overdue:'Kechikdi', cancelled:'Bekor' };
        return FB[status] || status;
    }
    return translated;
}
// Kept for backward compat (used in a few places as object map)
const TC_STATUS = new Proxy({}, { get: (_, s) => getStatusLabel(s) });

// Status icon only (for compact display) - now SVG
const TC_STATUS_ICON = {
    new:         IC.new,
    in_progress: IC.progress,
    review:      IC.review,
    done:        IC.done,
    overdue:     IC.overdue,
    cancelled:   IC.cancelled,
};

// Priority labels — resolved at runtime via i18n
function getPriorityLabel(priority) {
    const key = 'app.priority.' + priority;
    const translated = tr(key);
    if (translated === key) {
        const FB = { low:'Past', medium:"O'rta", high:'Muhum', urgent:'Juda muhum' };
        return FB[priority] || priority;
    }
    return translated;
}

function renderTasks() {
    const list = document.getElementById('task-list');
    const empty = document.getElementById('empty-tasks');

    // Eski "innerHTML='' + hidden" pattern flicker yaratardi.
    // Endi: yangi HTML tayyor bo'lganidan keyin, bir martada almashtiramiz.
    empty.classList.add('hidden');

    // Build subtask map from ALL tasks
    const subtaskMap = {};
    allTasks.forEach(t => {
        if (t.parent_id) {
            if (!subtaskMap[t.parent_id]) subtaskMap[t.parent_id] = [];
            subtaskMap[t.parent_id].push(t);
        }
    });

    // Root tasks only
    const myId = window._myUserId;
    let filtered = allTasks.filter(t => !t.parent_id);
    if (currentFilter === 'active') {
        filtered = filtered.filter(t => !['done', 'cancelled'].includes(t.status));
    } else if (currentFilter === 'done') {
        filtered = filtered.filter(t => {
            // 1) Umumiy task statusi done
            if (t.status === 'done') return true;
            // 2) Joriy foydalanuvchining shaxsiy statusi done bo'lsa ham ko'rsat
            if (myId && t.assignees) {
                const myAsgn = t.assignees.find(a => String(a.id) === String(myId));
                if (myAsgn && myAsgn.status === 'done') return true;
            }
            return false;
        });
    } else if (currentFilter === 'overdue') {
        // Status=overdue YOKI kechikib bajarilgan (status=done & completed_at > deadline)
        filtered = filtered.filter(t => {
            if (t.status === 'overdue') return true;
            if (t.status === 'done' && t.deadline && t.completed_at) {
                return new Date(t.completed_at) > new Date(t.deadline);
            }
            return false;
        });
    } else if (currentFilter === 'mine') {
        // Faqat men mas'ul bo'lgan vazifalar
        filtered = filtered.filter(t => {
            if (!myId || !t.assignees) return false;
            return t.assignees.some(a =>
                String(a.id) === String(myId) && a.is_responsible
            );
        });
    }

    // Also include sub-tasks the current user is assigned to
    if (myId) {
        const mySubtasks = allTasks.filter(t =>
            t.parent_id &&
            t.assignees && t.assignees.some(a => String(a.id) === String(myId)) &&
            !filtered.some(f => (subtaskMap[f.id] || []).some(c => c.id === t.id))
        );
        // Apply same status filter
        const filteredSubs = currentFilter === 'active'
            ? mySubtasks.filter(t => !['done','cancelled'].includes(t.status))
            : currentFilter === 'done' ? mySubtasks.filter(t => {
                if (t.status === 'done') return true;
                const myAsgn = t.assignees?.find(a => String(a.id) === String(myId));
                return myAsgn && myAsgn.status === 'done';
            })
            : currentFilter === 'overdue' ? mySubtasks.filter(t => t.status === 'overdue')
            : currentFilter === 'mine' ? mySubtasks.filter(t => {
                if (!myId || !t.assignees) return false;
                return t.assignees.some(a => String(a.id) === String(myId) && a.is_responsible);
            })
            : mySubtasks;
        // Render them as orphan sub-task cards (show parent ref from their parent_id)
        filteredSubs.forEach(s => {
            const parent = allTasks.find(t => t.id === s.parent_id);
            s._parentTitle = parent ? parent.title : null;
        });
        if (filteredSubs.length > 0) {
            if (filtered.length === 0) {
                list.classList.remove('hidden');
                empty.classList.add('hidden');
                list.innerHTML = filteredSubs.map(s => `
                    <div class="tc-group">
                        <div class="tc-child-wrap" style="padding-left:0">
                            <div class="task-card tc-card tc-card-subtask-orphan" data-priority="${s.priority}" data-status="${s.status}" onclick="openTask(${s.id})">
                                ${_taskCardInner(s, { parentName: s._parentTitle })}
                            </div>
                        </div>
                    </div>`).join('');
                return;
            }
            // Append orphan subtasks after regular tasks
            list.classList.remove('hidden');
            empty.classList.add('hidden');
            list.innerHTML = filtered.map(task => {
                const children = subtaskMap[task.id] || [];
                return _renderTaskTree(task, children);
            }).join('') + filteredSubs.map(s => `
                <div class="tc-group">
                    <div class="tc-child-wrap" style="padding-left:0">
                        <div class="task-card tc-card tc-card-subtask-orphan" data-priority="${s.priority}" data-status="${s.status}" onclick="openTask(${s.id})">
                            ${_taskCardInner(s, { parentName: s._parentTitle })}
                        </div>
                    </div>
                </div>`).join('');
            return;
        }
    }

    if (filtered.length === 0) {
        list.innerHTML = '';          // MUHIM: eski workspace kartalarini tozalaymiz
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
        <div class="task-card tc-card" data-priority="${task.priority}" data-status="${task.status}" onclick="openTask(${task.id})">
            ${_taskCardInner(task, { subtaskCount: children.length })}
        </div>`;

    if (!children.length) return `<div class="tc-group">${parentHtml}</div>`;

    const childrenHtml = children.map(c => `
        <div class="tc-child-wrap">
            <div class="tc-child-dot"></div>
            <div class="task-card tc-card tc-card-child" data-priority="${c.priority}" data-status="${c.status}" onclick="openTask(${c.id})">
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

// "Sizning navbatingiz" / "Palonchining navbati" / "Palonchi, Palonchilarning navbati"
function _buildTurnLabel(assignees, myId) {
    // "Navbat" = hali bajarmaganlar (done/cancelled emas)
    const active = assignees.filter(a => a.status !== 'done' && a.status !== 'cancelled');
    if (!active.length) {
        // Hammasi bajardi — birinchisining ismini ko'rsat
        const n = assignees[0].name.split(' ')[0];
        return `<span class="tc-meta-name tc-turn-done">✅ ${escapeHtml(n)} va jamoa</span>`;
    }

    const meActive = myId && active.some(a => String(a.id) === String(myId));

    if (meActive) {
        // Mening navbatim bor
        const others = active.filter(a => String(a.id) !== String(myId));
        if (others.length === 0) {
            return `<span class="tc-meta-name tc-turn-me">Sizning navbatingiz</span>`;
        } else if (others.length === 1) {
            const o = escapeHtml(others[0].name.split(' ')[0]);
            return `<span class="tc-meta-name tc-turn-me">Siz, ${o}ning navbati</span>`;
        } else {
            return `<span class="tc-meta-name tc-turn-me">Siz va boshqalarning navbati</span>`;
        }
    } else {
        // Boshqalarning navbati
        const names = active.slice(0, 3).map(a => escapeHtml(a.name.split(' ')[0]));
        if (active.length === 1) {
            return `<span class="tc-meta-name tc-turn-other">${names[0]}ning navbati</span>`;
        } else if (active.length === 2) {
            return `<span class="tc-meta-name tc-turn-other">${names.join(', ')}larning navbati</span>`;
        } else {
            const shown = names.slice(0, 2).join(', ');
            return `<span class="tc-meta-name tc-turn-other">${shown} +${active.length - 2}larning navbati</span>`;
        }
    }
}

function _taskCardInner(task, opts = {}) {
    const { subtaskCount = 0, parentName = null } = opts;
    const dlClass = task.deadline ? getDeadlineClass(task.deadline, task.status) : '';
    const dlUrgent = dlClass === 'deadline-urgent';
    const dlSoon   = dlClass === 'deadline-soon';

    // Assignees row — "navbat" label
    let assigneeHtml = '';
    if (task.assignees && task.assignees.length > 0) {
        const myId = window._myUserId;

        // Avatar chips
        const chips = task.assignees.slice(0, 3).map(a => {
            const isMe = myId && String(a.id) === String(myId);
            const init = isMe ? '★' : (a.name || '?')[0].toUpperCase();
            const aSt = a.status || 'new';
            const meCls = isMe ? ' tc-av-me' : '';
            return `<span class="tc-avatar tc-av-${aSt}${meCls}" title="${escapeHtml(a.name)}">${init}</span>`;
        }).join('');

        // "Navbat" label logic
        const turnLabel = _buildTurnLabel(task.assignees, myId);
        assigneeHtml = `<div class="tc-row">${chips}${turnLabel}</div>`;
    }

    // Subtask / parent ref row
    let refHtml = '';
    if (parentName) {
        refHtml = `<div class="tc-row tc-parent-ref"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 3 12 9 6"/><path d="M21 12H3"/></svg> Parent: ${escapeHtml(parentName)}</div>`;
    } else if (subtaskCount > 0) {
        refHtml = `<div class="tc-row tc-subtask-ref"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 3v12"/><path d="M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M15 6H6"/><path d="M6 18h8a4 4 0 0 0 0-8h-1"/></svg> ${subtaskCount} subtask</div>`;
    }

    // Deadline row — live countdown
    let dlHtml = '';
    if (task.deadline) {
        const icon = dlUrgent ? IC.fire : IC.clock;
        const dlCls = dlUrgent ? 'tc-dl-urgent' : (dlSoon ? 'tc-dl-soon' : 'tc-dl-normal');
        dlHtml = `<div class="tc-row ${dlCls} tc-countdown" data-deadline="${task.deadline}" data-status="${task.status}">${icon} <span class="tc-countdown-txt">${formatCountdown(task.deadline, task.status)}</span></div>`;
    }

    // "Mas'ul" badge — agar joriy foydalanuvchi mas'ul bo'lsa
    const myId = window._myUserId;
    const iAmResponsible = myId && task.assignees && task.assignees.some(
        a => String(a.id) === String(myId) && a.is_responsible
    );
    const respBadge = iAmResponsible
        ? `<span class="tc-resp-badge" title="Siz mas'ulsiz">⭐ Mas'ul</span>`
        : '';

    // Kechikib bajarilgan vazifa — alohida belgilash
    const lateDone = task.status === 'done' && task.deadline && task.completed_at
        && new Date(task.completed_at) > new Date(task.deadline);
    const statusLabel = lateDone
        ? `⏰ ${tr('app.status.done_late')||'Kechikib bajarildi'}`
        : (TC_STATUS[task.status] || task.status);
    const statusCls = lateDone ? 'tc-badge-late' : `tc-badge-${task.status}`;

    // Workflow (ketma-ketlik) belgisi
    const wfBadge = task.has_workflow
        ? `<span class="tc-wf-badge" title="Ketma-ketlik (workflow) vazifasi">🔄 Ketma-ketlik</span>`
        : '';

    return `
        <div class="tc-header">
            <span class="tc-title">${wfBadge ? '<span class="tc-wf-dot">🔄</span> ' : ''}${escapeHtml(task.title)}</span>
            <span class="tc-header-right">
                ${respBadge}
                <span class="tc-badge ${statusCls}">${statusLabel}</span>
            </span>
        </div>
        <div class="tc-body">
            ${wfBadge}${assigneeHtml}${refHtml}${dlHtml}
        </div>`;
}

// ===== Task Detail Modal =====
async function refreshOpenTask() {
    if (!currentTaskId) return;
    FX.refresh();
    const btn = document.getElementById('modal-refresh-btn');
    if (btn) btn.classList.add('refreshing');
    try {
        // Workflow modal bo'lsa — workflow ko'rinishini saqlab yangilaymiz
        const isWf = document.getElementById('task-modal')?.dataset.wfMode === '1';
        if (isWf) {
            const r = await apiRequest(`/workflows?task_id=${currentTaskId}`);
            const w = r && r.workflows && r.workflows[0];
            if (w) {
                const idx = _wfData.findIndex(x => x.task_id === currentTaskId);
                if (idx >= 0) _wfData[idx] = w; else _wfData.push(w);
                openWorkflowDetail(currentTaskId);
            }
        } else {
            await openTask(currentTaskId);  // oddiy vazifa
        }
        showToast('✓ Yangilandi');
    } catch (e) {
        console.warn('refreshOpenTask:', e);
    } finally {
        if (btn) setTimeout(() => btn.classList.remove('refreshing'), 400);
    }
}

async function openTask(taskId) {
    currentTaskId = taskId;
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        const data = await apiRequest(`/tasks/${taskId}`);
        const task = data.task;
        window._currentTaskFull = task;   // Mind map uchun saqlaymiz

        document.getElementById('modal-title').textContent = task.title;
        
        // Use i18n-resolved labels
        const priorityNames = new Proxy({}, { get: (_, p) => getPriorityLabel(p) });
        const statusNames   = new Proxy({}, { get: (_, s) => getStatusLabel(s) });

        const priorityColors = { low: 'priority-low', medium: 'priority-medium', high: 'priority-high', urgent: 'priority-urgent' };
        let bodyHtml = `
            <div class="modal-section">
                <div class="modal-detail">
                    <div class="modal-detail-label">${IC.pin} ${tr('app.modal.status')||'Status'}</div>
                    <div class="modal-detail-value badge-${task.status}">${statusNames[task.status] || task.status}</div>
                </div>
                <div class="modal-detail">
                    <div class="modal-detail-label">${IC.bolt} ${tr('app.modal.priority')||'Muhimlik'}</div>
                    <div class="modal-detail-value ${priorityColors[task.priority] || ''}">${priorityNames[task.priority] || task.priority}</div>
                </div>
            </div>
        `;

        if (task.description) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${tr('app.modal.desc')||'Tavsif'}</div>
                    <div class="modal-detail-value">${escapeHtml(task.description)}</div>
                </div>
            `;
        }

        if (task.deadline) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${tr('app.modal.deadline')||'Deadline'}</div>
                    <div class="modal-detail-value">${formatDeadlineFull(task.deadline)}</div>
                </div>
            `;
        }

        if (task.creator_name) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${tr('app.modal.creator')||'Yaratgan'}</div>
                    <div class="modal-detail-value">${IC.user} ${escapeHtml(task.creator_name)}</div>
                </div>
            `;
        }

        const statusShort = {
            new: 'Yangi', in_progress: 'Jarayonda', review: 'Ko\'rilmoqda',
            done: 'Bajarildi', overdue: 'Kechikdi', cancelled: 'Bekor',
        };

        // Masul (responsible)
        if (task.responsible_name) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${IC.star} Mas'ul (Responsible)</div>
                    <div class="modal-detail-value"><span class="resp-badge">${IC.star} ${escapeHtml(task.responsible_name)}</span></div>
                </div>
            `;
        }

        if (task.assignees && task.assignees.length > 0) {
            // Mas'ullar va kuzatuvchilarni ajratib ko'rsatamiz
            const responsible = task.assignees.filter(a => a.is_responsible);
            const observers   = task.assignees.filter(a => !a.is_responsible);

            const makeRow = (a, isResp) => {
                const st = a.status || 'new';
                const roleIcon = isResp ? IC.star : IC.eye;
                const roleTxt  = isResp
                    ? `<span class="asgn-role-badge asgn-resp">Mas'ul</span>`
                    : `<span class="asgn-role-badge asgn-obs">Kuzatuvchi</span>`;
                // Kuzatuvchi uchun status ko'rsatmaymiz
                const statusBadge = isResp
                    ? `<span class="assignee-row-status badge-${st}">${statusShort[st] || st}</span>`
                    : '';
                return `
                    <div class="assignee-row">
                        <span class="assignee-row-name">${roleIcon} ${escapeHtml(a.name)} ${roleTxt}</span>
                        ${statusBadge}
                    </div>
                `;
            };

            let rows = responsible.map(a => makeRow(a, true)).join('');
            if (observers.length) {
                rows += observers.map(a => makeRow(a, false)).join('');
            }

            const doneCount = responsible.filter(a => (a.status||'new') === 'done').length;
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">
                        Mas'ullar (${doneCount}/${responsible.length} bajardi)
                        ${observers.length ? `· ${observers.length} kuzatuvchi` : ''}
                    </div>
                    <div class="modal-detail-value assignees-status-list">${rows}</div>
                </div>
            `;
        }

        // Subtasks
        const subtasks = task.subtasks || [];
        const isCreator = (task.creator_id === (window._myUserId || -1));
        const hasParent = !!task.parent_id;
        {
            const subItems = subtasks.map(s => {
                const isDone = s.status === 'done' || s.status === 'DONE';
                return `
                    <div class="subtask-item ${isDone ? 'subtask-done' : ''}" onclick="openTask(${s.id})">
                        <span class="subtask-status subtask-check" title="${isDone ? 'Qayta ochish' : 'Bajarildi deb belgilash'}"
                            onclick="event.stopPropagation(); toggleSubtaskCheck(${s.id}, ${isDone})">${isDone ? IC.done : IC.circle}</span>
                        <span class="subtask-title">${escapeHtml(s.title.slice(0, 50))}</span>
                    </div>
                `;
            }).join('');
            // Cheksiz iyerarxiya — har qanday vazifa (parent yoki child) ham subtask qo'sha oladi
            const addBtn = `<button class="subtask-add-btn" onclick="openSubtaskTypePicker(${task.id})">${IC.plus} ${tr('app.subtask.add')||"Sub-task qo'shish"}</button>`;
            bodyHtml += `
                <div class="subtask-section">
                    <div class="subtask-section-title">${IC.folder} ${tr('app.subtasks')||'Sub-tasklar'}${subtasks.length ? ' ('+subtasks.length+')' : ''}</div>
                    ${subItems || '<div style="font-size:12px;color:var(--text2);margin-bottom:6px">'+(tr('app.subtask.empty')||"Hali sub-task yo'q")+'</div>'}
                    ${addBtn}
                </div>
            `;
        }

        // Comments section — extracted from history (type === 'comment')
        const comments = (task.history || []).filter(h => h.type === 'comment');
        if (comments.length > 0) {
            const commentsHtml = comments.map(c => {
                const authorName = escapeHtml(c.user_name || 'Foydalanuvchi');
                const commentText = escapeHtml(c.content || '');
                const commentTime = c.created_at ? formatDateTime(c.created_at) : '';
                return `
                    <div class="task-comment">
                        <div class="comment-header">
                            <span class="comment-author">${IC.user} ${authorName}</span>
                            <span class="comment-time">${commentTime}</span>
                        </div>
                        ${commentText ? `<div class="comment-text">${commentText}</div>` : ''}
                    </div>
                `;
            }).join('');
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${IC.comment} ${tr('app.modal.comments')||'Izohlar'} (${comments.length})</div>
                    <div class="task-comments-list">${commentsHtml}</div>
                </div>
            `;
        }

        // Media button — media gallery ochish
        const atts = task.attachments || [];
        {
            const mediaCount = atts.length;
            const mediaLabel = tr('app.media.title') || (IC.attach + ' Mediya');
            const hasCommentMedia = comments.filter(c => c.file_url).length;
            const totalMedia = mediaCount + hasCommentMedia;
            bodyHtml += `
                <div class="modal-detail media-section-row">
                    <button class="media-open-btn" onclick="openMediaGallery(${task.id})">
                        ${mediaLabel}${totalMedia > 0 ? ` <span class="media-count-badge">${totalMedia}</span>` : ''}
                    </button>
                </div>
            `;
        }

        // Metadata — minimal
        bodyHtml += `
            <div class="modal-detail">
                <div class="modal-detail-label">${IC.calendar} ${tr('app.modal.created')||'Yaratilgan'}</div>
                <div class="modal-detail-value" style="font-size:12px">${formatDate(task.created_at)}</div>
            </div>
        `;

        // 📊 Vaqt / aktivlik chartlari
        bodyHtml += `
            <div class="modal-detail">
                <div class="modal-detail-label">${IC.chart} ${tr('app.modal.time_activity')||'Vaqt va aktivlik'}</div>
                <div id="task-chart-${task.id}" class="task-chart-wrap">
                    <div class="task-chart-loading">${tr('app.loading')||'Yuklanmoqda...'}</div>
                </div>
            </div>
        `;

        // Tarix — barcha harakatlar ko'rsatiladi
        if (task.history && task.history.length > 0) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">${IC.clock} So'nggi harakatlari (${task.history.length})</div>
                    <div class="timeline" id="task-timeline-${task.id}">${_renderTimeline(task.history)}</div>
                </div>
            `;
        }

        document.getElementById('modal-body').innerHTML = bodyHtml;

        // Actions
        let actionsHtml = '';
        const myStatus       = task.my_status;
        const isWorkflow     = task.has_workflow === true;
        // Statusni faqat MAS'UL (responsible) o'zgartira oladi.
        // Yaratuvchi avtomatik mas'ul HISOBLANMAYDI — agar yaratuvchi ham status
        // o'zgartirmoqchi bo'lsa, o'zini ham mas'ul qilib qo'shishi kerak.
        const isResponsible  = task.my_is_responsible === true;
        const isObserver     = myStatus && !isResponsible;

        // Status + action buttons block
        const statusColors = { new:'#818CF8', in_progress:'#FBBF24', done:'#34D399', cancelled:'#6B7280', review:'#22D3EE' };
        const statusIcons  = { new:IC.new, in_progress:IC.progress, done:IC.done, cancelled:IC.cancelled, review:IC.review };

        if (myStatus || task.is_creator) {
            const sColor = statusColors[myStatus] || '#818CF8';
            const sIcon  = statusIcons[myStatus] || '📌';
            const sLabel = statusShort[myStatus] || (myStatus || '—');
            let roleLabel;
            if (isResponsible)         roleLabel = IC.star + ' ' + (tr('app.role.responsible')||"Mas'ul");
            else if (task.is_creator)  roleLabel = '✍️ ' + (tr('app.role.creator')||'Yaratuvchi');
            else                       roleLabel = IC.eye + ' ' + (tr('app.role.observer')||'Kuzatuvchi');
            actionsHtml += `
                <div class="task-status-card" style="--s-color:${sColor}">
                    <div class="tsc-role">${roleLabel}</div>
                    <div class="tsc-status">${sIcon} ${sLabel}</div>
                </div>`;
        }

        if (isObserver) {
            actionsHtml += `<div class="observer-badge">${IC.eye} Status faqat mas'ul shaxs tomonidan o'zgartiriladi</div>`;
        } else if (!isResponsible && task.is_creator) {
            actionsHtml += `<div class="observer-badge">✍️ ${tr('app.creator.hint')||"Siz yaratuvchisiz — statusni mas'ul o'zgartiradi. Siz vazifani o'chirishingiz mumkin."}</div>`;
        }

        if (myStatus && isResponsible && !isWorkflow) {
            let btnClass = 'wf-btn-start', btnText = IC.play+' Boshlashni boshlash';
            if (myStatus === 'new')         { btnClass = 'wf-btn-start'; btnText = IC.play+' Boshlash'; }
            if (myStatus === 'in_progress') { btnClass = 'wf-btn-done';  btnText = IC.check+' Bajarildi deb belgilash'; }
            if (myStatus === 'done')        { btnClass = 'wf-btn-secondary'; btnText = IC.check+' '+(tr('app.status.done_short')||'Bajarilgan'); }
            actionsHtml += `<button class="wf-status-btn ${btnClass}" onclick="handleTaskAction(${task.id}, '${myStatus}')">${btnText}</button>`;
        } else if (myStatus && isResponsible && isWorkflow) {
            if (myStatus === 'new') {
                actionsHtml += `<button class="wf-status-btn wf-btn-start" onclick="changeMyStatus(${task.id}, 'in_progress')">${IC.play} Boshlash</button>`;
            } else if (myStatus === 'in_progress') {
                actionsHtml += `<button class="wf-status-btn wf-btn-done" onclick="changeMyStatus(${task.id}, 'done')">${IC.check} Men bajardim</button>`;
            } else if (myStatus === 'done') {
                actionsHtml += `<button class="wf-status-btn wf-btn-secondary" onclick="changeMyStatus(${task.id}, 'in_progress')">${IC.refresh} Qayta ochish</button>`;
            }
        }

        // Yaratuvchi: TAHRIRLASH (deadline cho'zish) + O'CHIRISH
        if (task.is_creator) {
            actionsHtml += `<button class="modal-action-btn btn-secondary" onclick='openTaskEditForm(${task.id})'>${IC.edit||'✏️'} Tahrirlash / deadline</button>`;
            actionsHtml += `<button class="modal-action-btn btn-danger" onclick="deleteTaskByCreator(${task.id})">${IC.xmark} ${tr('app.delete_task')||"Vazifani o'chirish"}</button>`;
        }


        actionsHtml += `
            <div class="comment-row">
                <label class="comment-attach-btn" title="Fayl biriktirish">
                    <svg class="ic" style="width:17px;height:17px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                    <input type="file" style="display:none" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.zip"
                        onchange="sendCommentWithMedia(${task.id}, this)">
                </label>
                <input type="text" class="comment-input-inline" id="comment-input-${task.id}"
                    placeholder="${(tr('app.comment.ph')||'Izoh yozing...')}" maxlength="1000">
                <button class="comment-voice-btn" id="voice-btn-${task.id}" onclick="toggleVoiceRecord(${task.id})" title="Ovoz yozish">
                    <svg style="width:17px;height:17px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                </button>
                <button class="comment-video-btn"
                        ontouchstart="startVideoRecord(event, ${task.id})"
                        ontouchend="stopVideoRecord(event, ${task.id})"
                        onmousedown="startVideoRecord(event, ${task.id})"
                        onmouseup="stopVideoRecord(event, ${task.id})"
                        onmouseleave="stopVideoRecord(event, ${task.id}, true)"
                        title="Bosib turing — video tashlash">
                    <svg style="width:17px;height:17px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                </button>
                <button class="comment-send-btn-sm" onclick="sendComment(${task.id})"><svg style="width:15px;height:15px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
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
        const startedLabel = data.task_started_at
            ? `${IC.play} ${formatDateTime(data.task_started_at)}`
            : '—';
        let html = `
            <div class="tc-summary">
                <div class="tc-sum-item"><span class="tc-sum-val">${data.total_hours}</span><span class="tc-sum-lab">${IC.clock} ${tr('app.tc.total_hours')||'jami soat'}</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.lifespan_hours}</span><span class="tc-sum-lab">${IC.calendar} ${tr('app.tc.lifespan')||'umumiy davomiylik'}</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.comments}</span><span class="tc-sum-lab">${IC.comment} ${tr('app.tc.comment')||'izoh'}</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.attachments}</span><span class="tc-sum-lab">${IC.attach} ${tr('app.tc.file')||'fayl'}</span></div>
            </div>
            ${data.task_started_at ? `<div class="tc-started-note">⚙️ ${tr('app.tc.started')||'Ish boshlangan'}: <b>${startedLabel}</b></div>` : ''}
        `;

        // ── Kechiktirayotganlar ma'lumotini hisoblash ──
        // Workflow bo'lsa — har qadam ijrochisining vaqti
        // Oddiy task bo'lsa — har userning vaqti
        let delayData = [];
        if (steps.length > 0) {
            // Workflow — qadam bo'yicha guruhlash
            const byAssignee = {};
            steps.forEach(s => {
                const name = s.assignee || '—';
                if (!byAssignee[name]) byAssignee[name] = { name, hours: 0, done: 0, active: 0, pending: 0 };
                byAssignee[name].hours += (s.hours || 0);
                if (s.status === 'done') byAssignee[name].done++;
                else if (s.status === 'active') byAssignee[name].active++;
                else byAssignee[name].pending++;
            });
            delayData = Object.values(byAssignee).filter(u => u.hours > 0 || u.active > 0);
        } else {
            // Oddiy task — users
            delayData = users.filter(u => u.hours > 0);
        }

        if (delayData.length === 0) {
            wrap.innerHTML = html + '<div class="task-chart-empty">'+(tr('app.tc.no_activity')||'Hali aktivlik qayd etilmagan')+'</div>';
            return;
        }

        // YAGONA donut chart — kim kechiktirayotgan
        html += `
            <div class="tc-chart-block">
                <div class="tc-chart-title">${IC.clock} ${tr('app.tc.who_delays')||'Kim kechiktirayotgan'}</div>
                <div class="tc-canvas-wrap tc-pie-wrap" style="height:280px">
                    <canvas id="tc-pie-${taskId}"></canvas>
                </div>
            </div>
        `;

        wrap.innerHTML = html;

        // Eski instancelarni tozalash
        ['users', 'steps', 'activity', 'pie'].forEach(k => {
            const key = `${taskId}_${k}`;
            if (_taskChartInstances[key]) {
                try { _taskChartInstances[key].destroy(); } catch(_) {}
                delete _taskChartInstances[key];
            }
        });

        // Issiq → Sovuq palette: eng ko'p kechiktirayotgan qizil, kam-yashil
        const heatPalette = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#06b6d4','#8b5cf6'];
        // Eng ko'pdan kamga saralash — eng "kechiktirgan" qizilroq bo'ladi
        delayData.sort((a, b) => (b.hours || 0) - (a.hours || 0));

        // YAGONA donut chart
        {
            const ctx = document.getElementById(`tc-pie-${taskId}`);
            if (ctx) {
                _taskChartInstances[`${taskId}_pie`] = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: delayData.map(u => u.name),
                        datasets: [{
                            data: delayData.map(u => Number((u.hours || 0).toFixed(2))),
                            backgroundColor: delayData.map((_, i) => heatPalette[i % heatPalette.length]),
                            borderColor: '#0D1117',
                            borderWidth: 3,
                            hoverOffset: 12,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '58%',
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: '#e2e8f0',
                                    font: { size: 12, weight: '600' },
                                    padding: 12,
                                    usePointStyle: true,
                                    pointStyleWidth: 12,
                                },
                            },
                            tooltip: {
                                callbacks: {
                                    label: (c) => {
                                        const u = delayData[c.dataIndex];
                                        const total = c.dataset.data.reduce((a, b) => a + b, 0);
                                        const pct = total ? Math.round(c.parsed / total * 100) : 0;
                                        const lines = [` ${u.hours.toFixed(1)} soat (${pct}%)`];
                                        if (u.active != null) {
                                            lines.push(` 🟢 Faol qadam: ${u.active}`);
                                            if (u.done) lines.push(` ✅ Tugatdi: ${u.done}`);
                                            if (u.pending) lines.push(` ⏳ Kutilmoqda: ${u.pending}`);
                                        }
                                        return lines;
                                    },
                                },
                            },
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
    const m = document.getElementById('task-modal');
    if (!m) return;
    m.classList.add('hidden');
    delete m.dataset.wfMode;
    currentTaskId = null;
}

// ════════════════════════════════════════════════════════════════
//  🌐 MIND MAP — NotebookLM-style (markmap.js)
// ════════════════════════════════════════════════════════════════
let _mmInstance = null;

function _mmEsc(s) {
    const d = document.createElement('div');
    d.textContent = String(s == null ? '' : s).slice(0, 90);
    return d.innerHTML;
}
function _mmNode(content, children) {
    // Kontentni .mm-card wrapper ichiga olamiz — markmap to'liq enini o'lchaydi
    const n = { content: `<span class="mm-card">${content}</span>` };
    if (children && children.length) n.children = children;
    return n;
}

const _MM_STATUS_EMOJI = {
    new: '🆕', in_progress: '⚙️', review: '🔍', done: '✅', overdue: '⏰', cancelled: '🚫',
    active: '🟢', pending: '⚪', blocked: '⏸',
};
const _MM_PRIO_EMOJI = { low: '🟢', medium: '🟡', high: '🟠', urgent: '🔴' };

// Fayl node — bosib ochiladigan (payload.fileUrl orqali)
const _MM_FILE_EMOJI = { photo: '🖼', video: '🎥', voice: '🎤', audio: '🎵', document: '📄' };
function _mmFileNode(file) {
    const name = file.file_name || file.fileName || 'fayl';
    const node = _mmNode(`${_MM_FILE_EMOJI[file.file_type] || '📎'} ${_mmEsc(name)}`);
    const url = file.file_url || file.url;
    if (url) {
        node.payload = Object.assign({}, node.payload, { fileUrl: url });
    }
    return node;
}

// Inline badge'lar — har task/subtask uchun qisqa belgilar
function _mmBadges(n) {
    const parts = [];
    const resp = (n.assignees || []).filter(a => a.is_responsible);
    if (resp.length) {
        const names = resp.map(a => a.name.split(' ')[0]).slice(0, 2).join(', ');
        parts.push(`⭐${_mmEsc(names)}${resp.length > 2 ? '+' : ''}`);
    }
    if (n.comments_count)    parts.push(`💬${n.comments_count}`);
    if (n.attachments_count) parts.push(`📎${n.attachments_count}`);
    if (n.subtasks && n.subtasks.length) parts.push(`📂${n.subtasks.length}`);
    return parts.length ? `  <span style="opacity:.7;font-size:12px">${parts.join('  ')}</span>` : '';
}

// Bitta task/subtask node'ini rekursiv quradi — to'liq tafsilot bilan
function _mmTaskNode(n, isRoot) {
    const statusEmo = _MM_STATUS_EMOJI[n.status] || '•';
    const prioEmo   = _MM_PRIO_EMOJI[n.priority] || '';
    const typeIcon  = n.has_workflow ? '🔄' : '📋';

    const kids = [];

    // Holat + muhimlik
    kids.push(_mmNode(`${statusEmo} Holat: <b>${getStatusLabel(n.status)}</b>`));
    kids.push(_mmNode(`${prioEmo} Muhimlik: ${getPriorityLabel(n.priority)}`));
    if (n.deadline) {
        kids.push(_mmNode(`⏰ Deadline: ${_mmEsc(formatDateTime(n.deadline))}`));
    }
    if (n.completed_at) {
        kids.push(_mmNode(`✅ Bajarildi: ${_mmEsc(formatDate(n.completed_at))}`));
    }

    // Yaratuvchi (faqat root uchun)
    if (isRoot && n.creator_name) {
        kids.push(_mmNode(`✍️ Yaratuvchi: <b>${_mmEsc(n.creator_name)}</b>`));
    }

    // Mas'ullar / kuzatuvchilar
    const responsibles = (n.assignees || []).filter(a => a.is_responsible);
    const observers    = (n.assignees || []).filter(a => !a.is_responsible);
    if (responsibles.length) {
        kids.push(_mmNode(`⭐ Mas'ullar (${responsibles.length})`,
            responsibles.map(a => {
                const e = _MM_STATUS_EMOJI[a.status] || '•';
                const sub = a.completed_at ? [_mmNode(`✅ ${_mmEsc(formatDate(a.completed_at))}`)] : [];
                return _mmNode(`${e} ${_mmEsc(a.name)} — ${getStatusLabel(a.status)}`, sub);
            })));
    }
    if (observers.length) {
        kids.push(_mmNode(`👁 Kuzatuvchilar (${observers.length})`,
            observers.map(a => _mmNode(_mmEsc(a.name)))));
    }

    // Izoh / fayl soni
    if (n.comments_count)    kids.push(_mmNode(`💬 ${n.comments_count} izoh`));
    if (n.attachments_count) kids.push(_mmNode(`📎 ${n.attachments_count} fayl`));

    // 🔁 Rekursiv ichki subtasklar
    const subs = n.subtasks || [];
    if (subs.length) {
        kids.push(_mmNode(`📂 Sub-tasklar (${subs.length})`,
            subs.map(s => _mmTaskNode(s, false))));
    }

    const label = isRoot
        ? `${typeIcon} <b>${_mmEsc(n.title)}</b>`
        : `${statusEmo} <b>${_mmEsc(n.title)}</b>${_mmBadges(n)}`;

    return _mmNode(label, kids);
}

let _mmCache = null;            // {tree, steps, task} — qayta qurish uchun
let _mmCollapsed = new Set();   // yopilgan node ID'lar

// Ma'lumotni fetch qilib keshlaymiz, keyin sync root quramiz
async function _mmBuildTree(task) {
    let tree;
    try {
        const r = await apiRequest(`/tasks/${task.id}/tree`);
        tree = r.tree;
    } catch (e) { tree = null; }
    if (!tree) {
        tree = {
            id: task.id, title: task.title, status: task.status,
            priority: task.priority, deadline: task.deadline,
            completed_at: task.completed_at, creator_name: task.creator_name,
            has_workflow: task.has_workflow,
            comments_count: (task.history || []).filter(h => h.type === 'comment').length,
            attachments_count: (task.attachments || []).length,
            assignees: task.assignees || [],
            subtasks: (task.subtasks || []).map(s => ({ ...s, assignees: [], subtasks: [] })),
        };
    }
    let steps = [];
    if (task.has_workflow) {
        // wfSteps to'liq (izoh matni + fayl URL) — undan foydalanamiz
        if (task.wfSteps && task.wfSteps.length) {
            steps = task.wfSteps.map((s, i) => ({
                order: s.order != null ? s.order : (i + 1),
                title: s.title,
                status: s.status,
                assignee: s.assignee_name || s.assignee || '—',
                hours: s.hours || 0,
                comments: s.comments || [],
                attachments: s.attachments || [],
            }));
        } else {
            try {
                const chartData = await apiRequest(`/tasks/${task.id}/chart`);
                steps = chartData.steps || [];
            } catch (e) { /* skip */ }
        }
    }
    _mmCache = { tree, steps, task };
    _mmCollapsed = new Set();
    // 1-marta: ID'larni olish uchun quramiz, keyin HAMMASINI yopamiz
    const probe = _mmRootFromCache();
    _mmCollapseAllIds(probe);
    return _mmRootFromCache();   // endi hammasi yopiq holatda
}

// Barcha bolali node'larni collapsed Set'ga (boshida hammasi yopiq)
function _mmCollapseAllIds(node) {
    if (node.children && node.children.length) {
        if (node.payload && node.payload.mmid != null) _mmCollapsed.add(node.payload.mmid);
        node.children.forEach(_mmCollapseAllIds);
    }
}

// _mmCache'dan markmap root'ni QAYTADAN (sync) quradi — har toggle'da yangi obyektlar
function _mmRootFromCache() {
    if (!_mmCache) return _mmNode('—');
    const { tree, steps, task } = _mmCache;
    const rootNode = _mmTaskNode(tree, true);

    if (steps.length) {
        const kids = steps.map(s => {
            const e = _MM_STATUS_EMOJI[s.status] || '⚪';
            const sub = [_mmNode(`👤 ${_mmEsc(s.assignee)}`)];
            if (s.hours > 0) sub.push(_mmNode(`⏱ ${s.hours.toFixed(1)} soat`));
            // Izohlar — matn bilan (wfSteps) yoki son (chart)
            const sComments = s.comments || [];
            if (sComments.length) {
                sub.push(_mmNode(`💬 Izohlar (${sComments.length})`,
                    sComments.map(c => _mmNode(`<b>${_mmEsc(c.user || c.user_name || '?')}:</b> ${_mmEsc(c.content || c.text || '')}`))));
            } else if (s.comments_count) {
                sub.push(_mmNode(`💬 ${s.comments_count} izoh`));
            }
            // Fayllar — bosib ochiladigan (wfSteps) yoki son (chart)
            const sAtts = s.attachments || [];
            if (sAtts.length) {
                sub.push(_mmNode(`📎 Fayllar (${sAtts.length})`, sAtts.map(_mmFileNode)));
            } else if (s.attachments_count) {
                sub.push(_mmNode(`📎 ${s.attachments_count} fayl`));
            }
            return _mmNode(`${e} <b>${s.order}.</b> ${_mmEsc(s.title)}`, sub);
        });
        rootNode.children = rootNode.children || [];
        rootNode.children.splice(2, 0, _mmNode(`🪜 Qadamlar (${steps.length})`, kids));
    }

    const comments = (task.history || []).filter(h => h.type === 'comment');
    if (comments.length) {
        rootNode.children = rootNode.children || [];
        rootNode.children.push(_mmNode(`💬 Izohlar (${comments.length})`,
            comments.slice(-8).map(c => _mmNode(`<b>${_mmEsc(c.user_name)}:</b> ${_mmEsc(c.content)}`))));
    }

    // Fayllar — bosib ochiladigan (oddiy vazifa)
    const atts = task.attachments || [];
    if (atts.length) {
        rootNode.children = rootNode.children || [];
        rootNode.children.push(_mmNode(`📎 Fayllar (${atts.length})`, atts.map(_mmFileNode)));
    }

    const events = (task.history || []).filter(h => h.type === 'history');
    if (events.length) {
        const map = {
            created: 'yaratdi', status_changed: "status o'zgartirdi",
            my_status_changed: 'shaxsiy status', subtask_created: "subtask qo'shdi",
            attachment_added: "fayl qo'shdi", priority_changed: "muhimlik o'zgartirdi",
            title_changed: "sarlavha o'zgartirdi",
        };
        rootNode.children = rootNode.children || [];
        rootNode.children.push(_mmNode(`🕐 Tarix (${events.length})`,
            events.slice(-8).map(h => _mmNode(`${_mmEsc(h.user_name || '?')} — ${map[h.action] || h.action}`))));
    }

    // ⏰ KECHIKTIRAYOTGANNI aniqlash — eng tepaga qo'shamiz
    const now = new Date();
    const taskLate = task.deadline && new Date(task.deadline) < now && task.status !== 'done';
    const delayers = [];
    if (steps.length) {
        // Workflow: aktiv qadam egasi — hamma uni kutmoqda
        steps.filter(s => s.status === 'active').forEach(s => {
            delayers.push({
                name: s.assignee || '—',
                where: `${s.order}. ${s.title}`,
                late: !!taskLate,
            });
        });
    } else if (taskLate) {
        // Oddiy vazifa: deadline o'tgan + bajarmagan mas'ullar
        (tree.assignees || []).filter(a => a.is_responsible && a.status !== 'done').forEach(a => {
            delayers.push({ name: a.name, where: 'vazifa', late: true });
        });
    }
    if (delayers.length) {
        const lateN = delayers.filter(d => d.late).length;
        const branchTitle = lateN
            ? `⏰ <b>Kechiktirayotgan (${lateN})</b>`
            : `⏳ Hozir kim ustida (${delayers.length})`;
        rootNode.children = rootNode.children || [];
        rootNode.children.unshift(_mmNode(branchTitle, delayers.map(d => {
            const icon = d.late ? '🔴' : '🟡';
            const sub = [_mmNode(`📍 ${_mmEsc(d.where)}`)];
            sub.push(_mmNode(d.late ? '⏰ Deadline o\'tgan — kechikmoqda' : '⏳ Navbatda, hamma kutmoqda'));
            return _mmNode(`${icon} <b>${_mmEsc(d.name)}</b>`, sub);
        })));
        // Root kartochkasiga ⏰ belgi — yopiq holatda ham ko'rinadi
        if (lateN && rootNode.content) {
            rootNode.content = rootNode.content.replace(/<\/span>\s*$/,
                ' <span style="color:#ef4444;font-weight:800">⏰</span></span>');
        }
    }

    // Har node'ga stabil ID + yopilgan bo'lsa fold:1
    _mmAssignIds(rootNode, '0');
    return rootNode;
}

// Path-based stabil ID + collapsed holatdan fold
function _mmAssignIds(node, path) {
    node.payload = node.payload || {};
    node.payload.mmid = path;
    if (_mmCollapsed.has(path)) node.payload.fold = 1;
    else delete node.payload.fold;
    (node.children || []).forEach((c, i) => _mmAssignIds(c, path + '.' + i));
}

// QAYTA YARATIB toggle (ichki toggle ishlamaydi) — toza fit
function _mmRerender() {
    const svg = document.getElementById('mm-svg');
    if (!svg || !window.markmap) return;
    const root = _mmRootFromCache();
    if (_mmInstance) { try { _mmInstance.destroy(); } catch (e) {} _mmInstance = null; }
    svg.innerHTML = '';
    const palette = ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#a855f7','#ec4899','#14b8a6'];
    _mmInstance = window.markmap.Markmap.create(svg, _mmOptions(palette), root);
    requestAnimationFrame(() => {
        try { _mmInstance.fit(); } catch (e) {}
        requestAnimationFrame(_mmEnhance);
    });
}

function _mmOptions(palette) {
    return {
        duration: 0,              // animatsiya YO'Q — geometriya darrov barqaror (chiziqlar to'g'ri)
        nodeMinHeight: 16,
        spacingVertical: 12,
        spacingHorizontal: 90,
        paddingX: 8,
        fitRatio: 0.88,
        initialExpandLevel: -1,   // markmap auto-fold YO'Q — fold'ni o'zimiz beramiz
        color: (node) => {
            const d = node?.state?.depth ?? node?.depth ?? 0;
            return palette[d % palette.length];
        },
    };
}

async function openMindMap() {
    const task = window._currentTaskFull;
    if (!task) { showToast('Vazifa yuklanmagan', true); return; }
    if (typeof window.markmap === 'undefined' || !window.markmap.Markmap) {
        showToast('Mind map kutubxonasi yuklanmadi', true);
        return;
    }
    FX.tap();

    const modal = document.getElementById('mindmap-modal');
    const loading = document.getElementById('mm-loading');
    const titleEl = document.getElementById('mm-title-text');
    if (titleEl) titleEl.textContent = task.title.slice(0, 40);
    modal.classList.remove('hidden');
    loading.style.display = 'flex';

    try {
        const root = await _mmBuildTree(task);
        const svg = document.getElementById('mm-svg');
        svg.innerHTML = '';

        const isDark = !document.body.classList.contains('theme-light');
        const palette = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899', '#14b8a6'];

        if (_mmInstance) { try { _mmInstance.destroy(); } catch(e){} _mmInstance = null; }
        const { Markmap } = window.markmap;
        _mmInstance = Markmap.create(svg, _mmOptions(palette), root);

        // Matn rangini theme'ga moslash
        svg.style.setProperty('--mm-text', isDark ? '#e8e8f5' : '#1a1a2e');

        loading.style.display = 'none';
        _mmRenderLegend();

        // Animatsiya yo'q — darrov fit + chizish (geometriya barqaror)
        requestAnimationFrame(() => {
            try { _mmInstance.fit(); } catch(e){}
            requestAnimationFrame(_mmEnhance);
        });
    } catch (e) {
        console.error('mindmap error', e);
        loading.innerHTML = '<span style="color:#ef4444">❌ Xato: ' + (e.message || e) + '</span>';
    }
}

// Chiziqlarni KARTA MARKAZIDAN ulaymiz + strelka (chevron) toggle qo'shamiz.
// MutationObserver YO'Q — faqat render'dan keyin va chevron bosilganda ishlaydi.
function _mmEnhance() {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.getElementById('mm-svg');
    const mainG = svg && svg.querySelector('g');
    if (!mainG) return;

    // Chiziq qatlami (node'lardan orqada)
    let linkLayer = mainG.querySelector('g.mm-clinks');
    if (!linkLayer) {
        linkLayer = document.createElementNS(NS, 'g');
        linkLayer.setAttribute('class', 'mm-clinks');
        mainG.insertBefore(linkLayer, mainG.firstChild);
    }
    while (linkLayer.firstChild) linkLayer.removeChild(linkLayer.firstChild);

    // Chevron (strelka) qatlami — eng ustda
    let chevLayer = mainG.querySelector('g.mm-chevs');
    if (!chevLayer) {
        chevLayer = document.createElementNS(NS, 'g');
        chevLayer.setAttribute('class', 'mm-chevs');
        mainG.appendChild(chevLayer);
    }
    while (chevLayer.firstChild) chevLayer.removeChild(chevLayer.firstChild);

    const nodeEls = Array.prototype.slice.call(mainG.querySelectorAll('g.markmap-node'));
    const geom = (el) => {
        const tr = el.getAttribute('transform') || '';
        const m = /translate\(\s*([-\d.]+)[ ,]\s*([-\d.]+)/.exec(tr);
        const nx = m ? +m[1] : 0, ny = m ? +m[2] : 0;
        const fo = el.querySelector('foreignObject');
        const fx = fo ? +(fo.getAttribute('x') || 0) : 0;
        const fy = fo ? +(fo.getAttribute('y') || 0) : 0;
        const fw = fo ? +(fo.getAttribute('width') || 0) : 0;
        const fh = fo ? +(fo.getAttribute('height') || 0) : 0;
        // circle markaz koordinatasi node g ichida (transform'siz)
        return { rx: nx + fx + fw, lx: nx + fx, cy: ny + fy + fh / 2,
                 lcx: fx + fw + 14, lcy: fy + fh / 2 };
    };

    nodeEls.forEach((el) => {
        const d = el.__data__;
        if (!d) return;
        const g = geom(el);

        // Fayl node — bosilganda ochiladi (payload.fileUrl)
        const fileUrl = d.data && d.data.payload && d.data.payload.fileUrl;
        if (fileUrl) {
            const card = el.querySelector('.mm-card');
            const target = card || el.querySelector('foreignObject');
            if (target) {
                if (card) card.style.cursor = 'pointer';
                target.onclick = (ev) => {
                    ev.preventDefault(); ev.stopPropagation();
                    FX.tap();
                    try { window.open(fileUrl, '_blank'); } catch (e) {}
                };
            }
        }

        // Ko'rinib turgan bolalarga chiziq (markaz → markaz)
        (d.children || []).forEach((cd) => {
            const ce = nodeEls.find((e) => e.__data__ === cd);
            if (!ce) return;
            const cg = geom(ce);
            const x1 = g.rx + 14, y1 = g.cy, x2 = cg.lx, y2 = cg.cy;
            const mx = (x1 + x2) / 2;
            const p = document.createElementNS(NS, 'path');
            p.setAttribute('d', `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
            p.setAttribute('class', 'mm-clink');
            linkLayer.appendChild(p);
        });

        // Bolalari bo'lsa — strelka + toggle (KARTA va STRELKA ikkalasi bosiladi)
        const dataKids = (d.data && d.data.children) || [];
        if (dataKids.length) {
            const expanded = !!(d.children && d.children.length);
            const datum = d;

            const doToggle = (ev) => {
                if (ev) { ev.preventDefault(); ev.stopPropagation(); }
                FX.tap();
                const id = datum.data && datum.data.payload && datum.data.payload.mmid;
                if (id == null) return;
                if (_mmCollapsed.has(id)) _mmCollapsed.delete(id);
                else _mmCollapsed.add(id);
                _mmRerender();
            };

            // 1) Strelka tugmasi
            const cx = g.rx + 14, cy = g.cy;
            const ch = document.createElementNS(NS, 'g');
            ch.setAttribute('class', 'mm-chev');
            ch.setAttribute('transform', `translate(${cx},${cy})`);
            const bg = document.createElementNS(NS, 'circle');
            bg.setAttribute('r', 11);
            bg.setAttribute('class', 'mm-chev-bg');
            const pa = document.createElementNS(NS, 'path');
            pa.setAttribute('d', expanded ? 'M2.5,-4.5 L-3,0 L2.5,4.5' : 'M-2.5,-4.5 L3,0 L-2.5,4.5');
            pa.setAttribute('class', 'mm-chev-arrow');
            ch.appendChild(bg);
            ch.appendChild(pa);
            ch.addEventListener('click', doToggle);
            chevLayer.appendChild(ch);

            // 2) Kartani bosish ham toggle qiladi (eng katta yuza — ishonchli)
            const card = el.querySelector('.mm-card');
            if (card) {
                card.style.cursor = 'pointer';
                card.onclick = doToggle;
            }
            const fo = el.querySelector('foreignObject');
            if (fo) fo.onclick = doToggle;
        }
    });
}

function _mmRenderLegend() {
    const el = document.getElementById('mm-legend');
    if (!el) return;
    el.innerHTML = `
        <span class="mm-leg-item">✍️ Yaratuvchi</span>
        <span class="mm-leg-item">⭐ Mas'ul</span>
        <span class="mm-leg-item">👁 Kuzatuvchi</span>
        <span class="mm-leg-item">🪜 Qadam</span>
        <span class="mm-leg-item">💬 Izoh</span>
        <span class="mm-leg-item">📎 Fayl</span>
    `;
}

function mmFit() {
    if (_mmInstance) { try { _mmInstance.fit(); FX.tap(); } catch(e){} setTimeout(_mmEnhance, 460); }
}

function closeMindMap() {
    const modal = document.getElementById('mindmap-modal');
    if (modal) modal.classList.add('hidden');
    FX.tap();
}

async function mmExportPng() {
    const svg = document.getElementById('mm-svg');
    if (!svg) return;
    FX.tap();
    try {
        const clone = svg.cloneNode(true);
        const bbox = svg.getBBox();
        const pad = 40;
        const w = Math.ceil(bbox.width + pad * 2);
        const h = Math.ceil(bbox.height + pad * 2);
        clone.setAttribute('viewBox', `${bbox.x - pad} ${bbox.y - pad} ${w} ${h}`);
        clone.setAttribute('width', w);
        clone.setAttribute('height', h);

        const isDark = !document.body.classList.contains('theme-light');
        const bg = isDark ? '#0d0d18' : '#ffffff';
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', bbox.x - pad); rect.setAttribute('y', bbox.y - pad);
        rect.setAttribute('width', w); rect.setAttribute('height', h);
        rect.setAttribute('fill', bg);
        clone.insertBefore(rect, clone.firstChild);

        const xml = new XMLSerializer().serializeToString(clone);
        const svg64 = btoa(unescape(encodeURIComponent(xml)));
        const img = new Image();
        img.onload = () => {
            const canvas = document.createElement('canvas');
            const scale = 2;
            canvas.width = w * scale; canvas.height = h * scale;
            const ctx = canvas.getContext('2d');
            ctx.scale(scale, scale);
            ctx.drawImage(img, 0, 0);
            canvas.toBlob((blob) => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `mindmap_${Date.now()}.png`;
                a.click();
                URL.revokeObjectURL(url);
                showToast('✅ PNG saqlandi');
            }, 'image/png');
        };
        img.src = 'data:image/svg+xml;base64,' + svg64;
    } catch (e) {
        showToast('❌ Eksport xatosi', true);
    }
}

// Close modal on overlay click
document.getElementById('task-modal')?.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) closeModal();
});

// ===== Change Status =====
// Sub-task checkbox ni bosish — statusni toggle qiladi (done ↔ in_progress)
async function toggleSubtaskCheck(subtaskId, isDone) {
    const newStatus = isDone ? 'in_progress' : 'done';
    try {
        await apiRequest(`/tasks/${subtaskId}/status`, 'PATCH', { status: newStatus });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        // Ota-taskni qayta yuklaymiz
        if (currentTaskId) await openTask(currentTaskId);
    } catch(e) {
        showToast('Xatolik yuz berdi', true);
    }
}

// ============ YARATUVCHI: VAZIFANI TAHRIRLASH (deadline cho'zish) ============
function _toDTLocal(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
    } catch(e) { return ''; }
}

function openTaskEditForm(taskId) {
    const t = window._currentTaskFull;
    if (!t || t.id !== taskId) { showToast('Vazifa yuklanmagan', true); return; }
    FX.tap();
    const body = document.getElementById('modal-body');
    body.innerHTML = `
        <div class="te-form">
            <div class="te-row">
                <label>📝 Sarlavha</label>
                <input type="text" id="te-title" value="${escapeHtml(t.title||'')}" maxlength="500">
            </div>
            <div class="te-row">
                <label>📄 Tavsif</label>
                <textarea id="te-desc" rows="3">${escapeHtml(t.description||'')}</textarea>
            </div>
            <div class="te-row">
                <label>⚡ Muhimlik</label>
                <select id="te-prio">
                    <option value="low"${t.priority==='low'?' selected':''}>🟢 Past</option>
                    <option value="medium"${t.priority==='medium'?' selected':''}>🟡 O'rta</option>
                    <option value="high"${t.priority==='high'?' selected':''}>🟠 Yuqori</option>
                    <option value="urgent"${t.priority==='urgent'?' selected':''}>🔴 Juda muhim</option>
                </select>
            </div>
            <div class="te-row">
                <label>⏰ Deadline (cho'zish/o'zgartirish)</label>
                <input type="datetime-local" id="te-deadline" value="${_toDTLocal(t.deadline)}">
                <div style="font-size:11px;color:var(--text3);margin-top:4px">Bo'sh qoldirsangiz — deadline olib tashlanadi</div>
            </div>
            <div class="te-actions">
                <button class="modal-action-btn btn-secondary" onclick="openTask(${taskId})">← Bekor</button>
                <button class="modal-action-btn btn-primary" id="te-save" onclick="saveTaskEditMini(${taskId})">💾 Saqlash</button>
            </div>
        </div>
    `;
    document.getElementById('modal-actions').innerHTML = '';
}

async function saveTaskEditMini(taskId) {
    const btn = document.getElementById('te-save');
    if (btn) { btn.disabled = true; btn.textContent = '⏳...'; }
    const dl = document.getElementById('te-deadline').value;
    const payload = {
        title:       document.getElementById('te-title').value,
        description: document.getElementById('te-desc').value,
        priority:    document.getElementById('te-prio').value,
        deadline:    dl ? new Date(dl).toISOString() : null,
    };
    try {
        const r = await apiRequest(`/tasks/${taskId}/edit`, 'PATCH', payload);
        showToast(r.message || '✅ Saqlandi');
        FX.success();
        await openTask(taskId);   // modalni yangilaymiz
    } catch (e) {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Saqlash'; }
        showToast('❌ ' + (e.message || e), true);
    }
}

async function deleteTaskByCreator(taskId) {
    const ok = (typeof tg?.showConfirm === 'function')
        ? await new Promise(r => tg.showConfirm("Bu vazifani butunlay o'chirib tashlaysizmi? Buni qaytarib bo'lmaydi.", v => r(v)))
        : confirm("Bu vazifani butunlay o'chirib tashlaysizmi? Buni qaytarib bo'lmaydi.");
    if (!ok) return;
    try {
        await apiRequest(`/tasks/${taskId}`, 'DELETE');
        // Local listdan olib tashlaymiz
        const idx = allTasks.findIndex(t => t.id === taskId);
        if (idx !== -1) allTasks.splice(idx, 1);
        renderTasks();
        closeModal();
        showToast("✅ Vazifa o'chirildi");
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        try {
            const stats = await apiRequest(`/stats?company_id=${currentWorkspaceId}`);
            updateQuickStats(stats); updateStatsTab(stats);
        } catch {}
    } catch (err) {
        showToast('❌ ' + (err.message || err), true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
    }
}

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
        in_progress: IC.progress+' Jarayonda', done: IC.done+' Bajarildi',
        review: IC.review+' Ko\'rilmoqda', cancelled: IC.cancelled+' Bekor qilish',
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
        assignee_name: '',
        deadline: null,
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

    list.innerHTML = workflowSteps.map((step, idx) => {
        const hasDl  = !!step.deadline;
        const dlLabel = hasDl
            ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${formatDeadline(step.deadline)}`
            : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> Deadline`;
        const dlCls = hasDl ? 'wf-step-dl-pill has-dl' : 'wf-step-dl-pill';
        const assigneeOpts = companyMembers.map(m =>
            `<option value="${m.id}" ${step.assignee_id == m.id ? 'selected' : ''}>${escapeHtml(m.name)}</option>`
        ).join('');
        return `
        <div class="wf-step-card" data-index="${idx}">
            <div class="wf-step-head">
                <span class="wf-step-badge">${idx + 1}</span>
                <input type="text" class="wf-step-title-inp" placeholder="Qadam nomini kiriting..."
                       value="${escapeHtml(step.title)}"
                       oninput="updateWorkflowStep(${idx}, 'title', this.value)">
                <button class="wf-step-del" onclick="removeWorkflowStep(${idx})" title="O'chirish">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="wf-step-foot">
                <select class="wf-step-sel" onchange="updateWorkflowStep(${idx}, 'assignee', this.value)">
                    <option value="">Kuzatuvchini tanlang</option>
                    ${assigneeOpts}
                </select>
                <button class="${dlCls}" onclick="_openStepDeadline(${idx})">${dlLabel}</button>
            </div>
        </div>`;
    }).join('');
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
        } else if (field === 'deadline') {
            workflowSteps[idx].deadline = value || null;
        }
    }
}

// Open deadline picker for a specific workflow step
function _openStepDeadline(idx) {
    _dlOnConfirm = function(isoStr) {
        workflowSteps[idx].deadline = isoStr || null;
        renderWorkflowSteps();
    };
    openDeadlinePicker();
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

    // "Hammasi" da workspace tanlash majburiy
    if (currentWorkspaceId === 'all' && !_createWsOverride) {
        showToast('⚠️ Avval ishchi makonni tanlang', true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
        const label = document.getElementById('create-workspace-label');
        if (label) {
            label.classList.add('ws-pulse');
            setTimeout(() => label.classList.remove('ws-pulse'), 1500);
            label.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
    }

    if (!title || title.length < 3) {
        showToast('Vazifa nomi kamida 3 belgi bo\'lsin', true);
        if (tg) tg.HapticFeedback?.notificationOccurred('error');
        return;
    }

    // Effective workspace (override yoki current)
    const _effWsId = (currentWorkspaceId === 'all' && _createWsOverride)
        ? _createWsOverride.id : currentWorkspaceId;

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

    // Capture subtask parent before any async ops
    const _stParentId = _subtaskParentId;

    try {
        if (currentTaskType === 'workflow') {
            // Create workflow
            const body = {
                title,
                priority,
                steps: workflowSteps.map(s => {
                    const step = {
                        title: s.title.trim(),
                        assignee_user_id: s.assignee_id,
                    };
                    if (s.deadline) step.deadline = s.deadline;
                    return step;
                }),
            };
            if (description) body.description = description;
            if (deadline) body.deadline = new Date(deadline).toISOString();
            if (_effWsId !== 'personal') {
                body.company_id = _effWsId;
            }
            if (_stParentId) body.parent_id = _stParentId;

            await apiRequest('/tasks/create-workflow', 'POST', body);
            showToast('✅ ' + (_stParentId ? 'Ketma-ketlik sub-task yaratildi!' : 'Workflow yaratildi!'));

            if (_stParentId) {
                // Return to parent task
                _clearSubtaskMode();
                await loadTasks();
                document.querySelector('.bnav-btn[data-tab="tasks"]')?.click();
                openTask(_stParentId);
            } else {
                document.querySelector('.bnav-btn[data-tab="tasks"]').click();
                switchTasksSubtab('workflow');
                await loadWorkflows();
            }
        } else {
            // Create regular task
            const body = { title, priority };
            if (description) body.description = description;
            if (deadline) body.deadline = new Date(deadline).toISOString();
            if (_stParentId) body.parent_id = _stParentId;
            if (_effWsId !== 'personal') {
                body.company_id = _effWsId;
                const allSelIds = [...selectedAssigneeIds, ...externalAssignees.map(e => e.id)];
                if (allSelIds.length === 0) {
                    showToast("Kamida bitta ijrochi tanlang", true);
                    btn.disabled = false;
                    btn.querySelector('.btn-text').classList.remove('hidden');
                    btn.querySelector('.btn-loading').classList.add('hidden');
                    return;
                }
                body.assignee_ids = allSelIds;
                if (selectedResponsibleIds.length > 0) {
                    body.responsible_ids = selectedResponsibleIds.slice();
                }
            }

            const result = await apiRequest('/tasks', 'POST', body);

            // Add to local list
            if (result.task) {
                allTasks.unshift(result.task);
            }

            showToast('✅ ' + (_stParentId ? 'Sub-task yaratildi!' : 'Vazifa yaratildi!'));

            if (_stParentId) {
                // Return to parent task after creating sub-task
                _clearSubtaskMode();
                await loadTasks();
                document.querySelector('.bnav-btn[data-tab="tasks"]')?.click();
                openTask(_stParentId);
            } else {
                // Switch to tasks tab
                document.querySelector('.bnav-btn[data-tab="tasks"]').click();
                // Refresh stats
                const stats = await apiRequest(`/stats?company_id=${currentWorkspaceId}`);
                updateQuickStats(stats);
                updateStatsTab(stats);
                renderTasks();
            }
        }

        if (tg) tg.HapticFeedback?.notificationOccurred('success');

        // Clear form
        document.getElementById('task-title').value = '';
        document.getElementById('task-desc').value = '';
        document.getElementById('task-deadline').value = '';
        document.getElementById('title-count').textContent = '0';
        selectedAssigneeIds = [];
        externalAssignees = [];
        selectedResponsibleIds = [];
        currentTaskType = 'regular';
        workflowSteps = [];
        selectTaskType('regular');
        renderAssignees();
        renderResponsibleSection();

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

    // Audio + haptic — turi aniqlanadi message ichidagi belgi orqali
    if (isError) {
        FX.error();
    } else if (/✅|✓/.test(message)) {
        FX.success();
    } else if (/🎉|tugat|yakunlandi/.test(message)) {
        FX.celebrate();
    } else {
        FX.notify();
    }
}

// ════════════════════════════════════════════════════════════════
//  FX — Audio + Haptic feedback (Apple-style polished UX)
// ════════════════════════════════════════════════════════════════
const FX = (() => {
    let ctx = null;
    let masterGain = null;
    const SOUND_KEY = 'fx_sound_enabled';
    const HAPTIC_KEY = 'fx_haptic_enabled';

    function isSoundOn()  { return localStorage.getItem(SOUND_KEY)  !== '0'; }   // default ON
    function isHapticOn() { return localStorage.getItem(HAPTIC_KEY) !== '0'; }
    function setSoundOn(v)  { localStorage.setItem(SOUND_KEY,  v ? '1' : '0'); }
    function setHapticOn(v) { localStorage.setItem(HAPTIC_KEY, v ? '1' : '0'); }

    function _ensure() {
        if (ctx) return ctx;
        try {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
            masterGain = ctx.createGain();
            masterGain.gain.value = 0.18;   // jami volume past — tinch
            masterGain.connect(ctx.destination);
        } catch(e) { return null; }
        return ctx;
    }

    // Bitta ton — frequency, duration, type, gain envelope
    function _tone({ freq = 440, dur = 0.12, type = 'sine', vol = 1, attack = 0.005, decay = 0.08, delay = 0 } = {}) {
        if (!isSoundOn()) return;
        const c = _ensure(); if (!c) return;
        try { if (c.state === 'suspended') c.resume(); } catch(_){}
        const t0 = c.currentTime + delay;
        const osc = c.createOscillator();
        const g = c.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq, t0);
        g.gain.setValueAtTime(0, t0);
        g.gain.linearRampToValueAtTime(vol, t0 + attack);
        g.gain.exponentialRampToValueAtTime(0.001, t0 + attack + decay);
        osc.connect(g).connect(masterGain);
        osc.start(t0);
        osc.stop(t0 + attack + decay + 0.02);
    }

    // Frekvensiya sweep (whoosh, slide)
    function _sweep({ from = 200, to = 800, dur = 0.2, vol = 0.5, type = 'sine' } = {}) {
        if (!isSoundOn()) return;
        const c = _ensure(); if (!c) return;
        try { if (c.state === 'suspended') c.resume(); } catch(_){}
        const t0 = c.currentTime;
        const osc = c.createOscillator();
        const g = c.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(from, t0);
        osc.frequency.exponentialRampToValueAtTime(Math.max(20, to), t0 + dur);
        g.gain.setValueAtTime(0, t0);
        g.gain.linearRampToValueAtTime(vol, t0 + 0.01);
        g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
        osc.connect(g).connect(masterGain);
        osc.start(t0);
        osc.stop(t0 + dur + 0.02);
    }

    function _haptic(type) {
        if (!isHapticOn()) return;
        const t = window.Telegram?.WebApp?.HapticFeedback;
        if (!t) {
            // Fallback — Vibration API
            try { navigator.vibrate?.([type === 'heavy' ? 25 : 10]); } catch(_){}
            return;
        }
        try {
            switch (type) {
                case 'light':   t.impactOccurred('light');         break;
                case 'medium':  t.impactOccurred('medium');        break;
                case 'heavy':   t.impactOccurred('heavy');         break;
                case 'success': t.notificationOccurred('success'); break;
                case 'warning': t.notificationOccurred('warning'); break;
                case 'error':   t.notificationOccurred('error');   break;
                case 'select':  t.selectionChanged();              break;
            }
        } catch(_){}
    }

    return {
        isSoundOn, isHapticOn, setSoundOn, setHapticOn,

        // Yumshoq tap — har tugma uchun
        tap() {
            _tone({ freq: 880, dur: 0.04, type: 'sine', vol: 0.35, decay: 0.04 });
            _haptic('light');
        },

        // Tanlash — chip, filter, dropdown
        select() {
            _tone({ freq: 1100, dur: 0.05, type: 'sine', vol: 0.3, decay: 0.05 });
            _haptic('select');
        },

        // ✅ Bajarildi (yumshoq qo'ng'iroq)
        success() {
            _tone({ freq: 988, dur: 0.12, type: 'sine', vol: 0.35, decay: 0.12 });
            _tone({ freq: 1318, dur: 0.16, type: 'sine', vol: 0.32, decay: 0.16, delay: 0.07 });
            _haptic('success');
        },

        // ❌ Xato (past, qisqa)
        error() {
            _tone({ freq: 220, dur: 0.08, type: 'square', vol: 0.32, decay: 0.08 });
            _tone({ freq: 180, dur: 0.12, type: 'square', vol: 0.30, decay: 0.12, delay: 0.07 });
            _haptic('error');
        },

        // 🔄 Refresh — yumshoq whoosh
        refresh() {
            _sweep({ from: 600, to: 1400, dur: 0.18, vol: 0.22, type: 'sine' });
            _haptic('light');
        },

        // 📥 Notification — pop
        notify() {
            _tone({ freq: 1320, dur: 0.07, type: 'sine', vol: 0.30, decay: 0.07 });
            _tone({ freq: 1760, dur: 0.10, type: 'sine', vol: 0.25, decay: 0.10, delay: 0.04 });
            _haptic('light');
        },

        // 🎉 Celebrate — 3 ta nota ramp
        celebrate() {
            _tone({ freq: 784,  dur: 0.10, type: 'triangle', vol: 0.30, decay: 0.10, delay: 0.00 }); // G5
            _tone({ freq: 988,  dur: 0.10, type: 'triangle', vol: 0.30, decay: 0.10, delay: 0.08 }); // B5
            _tone({ freq: 1318, dur: 0.18, type: 'triangle', vol: 0.35, decay: 0.18, delay: 0.16 }); // E6
            _haptic('success');
        },

        // 📨 Send (yuborilgan)
        send() {
            _sweep({ from: 400, to: 1100, dur: 0.12, vol: 0.28, type: 'sine' });
            _haptic('medium');
        },

        // 🗑 Delete
        delete() {
            _sweep({ from: 800, to: 200, dur: 0.16, vol: 0.30, type: 'sawtooth' });
            _haptic('warning');
        },
    };
})();
window.FX = FX;

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

/* ============================================================
   LIVE COUNTDOWN — task kartochkalarida real vaqt sanoq
   ============================================================ */
function formatCountdown(iso, status) {
    if (!iso) return '';
    const d    = new Date(iso);
    const now  = new Date();
    const diff = d - now; // ms

    if (status === 'done' || status === 'cancelled') return formatDate(iso);

    if (diff < 0) {
        // Kechikkan
        const abs  = -diff;
        const days = Math.floor(abs / 86400000);
        const hrs  = Math.floor((abs % 86400000) / 3600000);
        const mins = Math.floor((abs % 3600000) / 60000);
        if (days > 0) return `${days}kun ${hrs}soat ${mins}min kechikdi`;
        if (hrs  > 0) return `${hrs}soat ${mins}min kechikdi`;
        return `${mins || 1}min kechikdi`;
    }

    // Qolgan vaqt
    const days = Math.floor(diff / 86400000);
    const hrs  = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);

    if (days >= 7) return `${days}kun ${hrs}soat qoldi`;
    if (days >  0) return `${days}kun ${hrs}soat ${mins}min qoldi`;
    if (hrs  >  0) return `${hrs}soat ${mins}min qoldi`;
    return `${mins || 1}min qoldi`;
}

let _countdownInterval = null;
function startCountdownTicker() {
    if (_countdownInterval) clearInterval(_countdownInterval);
    _tickCountdowns(); // darhol bir marta chaqir
    _countdownInterval = setInterval(_tickCountdowns, 60000); // har 1 daqiqada
}
function _tickCountdowns() {
    document.querySelectorAll('.tc-countdown[data-deadline]').forEach(el => {
        const iso    = el.dataset.deadline;
        const status = el.dataset.status || '';
        const txt    = el.querySelector('.tc-countdown-txt');
        if (!txt) return;
        txt.textContent = formatCountdown(iso, status);
        // Urgency klassini yangilash
        const diff = new Date(iso) - new Date();
        el.classList.remove('tc-dl-urgent', 'tc-dl-soon', 'tc-dl-normal');
        if (status === 'done' || status === 'cancelled') {
            el.classList.add('tc-dl-normal');
        } else if (diff < 0 || diff < 86400000) {
            el.classList.add('tc-dl-urgent');
        } else if (diff < 259200000) {
            el.classList.add('tc-dl-soon');
        } else {
            el.classList.add('tc-dl-normal');
        }
    });
}

// ============ AI Chat (o'chirildi) ============

function openAiChat()  { /* removed */ }
function closeAiChat() { /* removed */ }
function clearAiChat() { /* removed */ }

function removeAiTyping() { /* removed */ }
function sendAiMessage()  { /* removed */ }
function aiChatKey()      { /* removed */ }

// ============ Media + Comments Feed ============
async function openMediaCommentsFeed(taskId) {
    let task = allTasks.find(t => t.id === taskId);
    let atts = task?.attachments || [];
    let comms = [];

    // Always reload fresh for feed
    try {
        const fresh = await apiRequest(`/tasks/${taskId}`);
        if (fresh && fresh.task) {
            atts  = fresh.task.attachments || [];
            comms = (fresh.task.history || []).filter(h => h.type === 'comment');
        }
    } catch(e) {}

    const existing = document.getElementById('feed-modal');
    if (existing) existing.remove();

    // Merge & sort by created_at
    const items = [
        ...atts.map(a => ({ kind: 'media', ...a })),
        ...comms.map(c => ({ kind: 'comment', ...c })),
    ].sort((a, b) => (a.created_at || '') < (b.created_at || '') ? -1 : 1);

    const overlay = document.createElement('div');
    overlay.id = 'feed-modal';
    overlay.className = 'feed-overlay';
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };

    const itemsHtml = items.length ? items.map(item => {
        if (item.kind === 'media') {
            const ft   = item.file_type || 'document';
            const mime = item.mime_type  || '';
            const url  = item.file_url  || '';
            const name = escapeHtml(item.file_name || ft);
            const who  = escapeHtml(item.uploader_name || '?');
            const when = item.created_at ? formatDateTime(item.created_at) : '';

            let preview = '';
            if (ft === 'photo' || mime.startsWith('image/')) {
                preview = `<a href="${url}" target="_blank"><img src="${url}" class="feed-img" loading="lazy"/></a>`;
            } else if (ft === 'video_note') {
                preview = `<video src="${url}" class="feed-vidnote" controls preload="metadata" playsinline></video>`;
            } else if (ft === 'video' || mime.startsWith('video/')) {
                preview = `<video src="${url}" class="feed-video" controls preload="metadata" playsinline></video>`;
            } else if (ft === 'voice' || mime.startsWith('audio/')) {
                preview = `<div class="feed-audio-wrap">🎤 <audio src="${url}" controls class="feed-audio" preload="metadata"></audio></div>`;
            } else {
                preview = `<a href="${url}" target="_blank" class="feed-file-link">${IC.attach} ${name}</a>`;
            }
            return `
                <div class="feed-item feed-item-media">
                    <div class="feed-preview">${preview}</div>
                    <div class="feed-meta">${IC.user} ${who} · <span class="feed-time">${when}</span></div>
                </div>`;
        } else {
            const who  = escapeHtml(item.user_name || '?');
            const when = item.created_at ? formatDateTime(item.created_at) : '';
            const txt  = escapeHtml(item.content || '');
            return `
                <div class="feed-item feed-item-comment">
                    <div class="feed-comment-bubble">
                        <div class="feed-comment-author">${IC.user} ${who}</div>
                        <div class="feed-comment-text">${txt}</div>
                        <div class="feed-time">${when}</div>
                    </div>
                </div>`;
        }
    }).join('') : `<div class="feed-empty">📭 Hali mediya yoki izoh yo'q</div>`;

    overlay.innerHTML = `
        <div class="feed-sheet">
            <div class="feed-header">
                <span class="feed-title">🖼 Mediya va Izohlar${items.length ? ' ('+items.length+')' : ''}</span>
                <button class="feed-close" onclick="document.getElementById('feed-modal').remove()">✕</button>
            </div>
            <div class="feed-body">${itemsHtml}</div>
        </div>`;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('feed-visible'));
}

// ============ Media Gallery ============
async function openMediaGallery(taskId) {
    // Taskni topamiz (allTasks dan)
    const task = allTasks.find(t => t.id === taskId);
    let atts = task?.attachments || [];

    // Agar allTasks da attachment yo'q bo'lsa, API dan yuklaymiz
    if (!atts.length && task) {
        try {
            const fresh = await apiRequest(`/tasks/${taskId}`);
            if (fresh && fresh.task) atts = fresh.task.attachments || [];
        } catch(e) {}
    }

    const existing = document.getElementById('media-gallery-modal');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'media-gallery-modal';
    overlay.className = 'media-overlay';
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };

    const mediaLabel = tr('app.media.title') || (IC.attach + ' Mediya');
    const emptyLabel = tr('app.media.empty') || 'Mediya fayllari yo\'q';
    const uploadLabel = tr('app.media.upload') || 'Fayl yuklash';
    const commentPh = tr('app.media.comment_ph') || 'Izoh yozing yoki fayl tanlang...';

    const itemsHtml = atts.length ? atts.map(a => {
        const ft = a.file_type || 'document';
        const mime = a.mime_type || '';
        const isImg       = ft === 'photo'      || mime.startsWith('image/');
        const isVid       = ft === 'video'      || (mime.startsWith('video/') && ft !== 'video_note');
        const isVideoNote = ft === 'video_note';
        const isVoice     = ft === 'voice'      || mime.startsWith('audio/');

        const uploaderName = escapeHtml(a.uploader_name || '?');
        const dateStr = a.created_at ? formatDateTime(a.created_at) : '';
        const byLabel = (tr('app.media.by') || '{name} tomonidan').replace('{name}', uploaderName);
        const sizeStr = a.file_size ? _formatFileSize(a.file_size) : '';

        let preview = '';
        if (isImg) {
            preview = `<a href="${a.file_url}" target="_blank" class="mg-img-link">
                <img src="${a.file_url}" class="mg-img" alt="${escapeHtml(a.file_name||'')}"/>
            </a>`;
        } else if (isVideoNote) {
            // Dumaloq video
            preview = `<div class="mg-vidnote-wrap">
                <video src="${a.file_url}" class="mg-vidnote" controls preload="metadata" playsinline></video>
            </div>`;
        } else if (isVid) {
            preview = `<video src="${a.file_url}" class="mg-video" controls preload="metadata" playsinline></video>`;
        } else if (isVoice) {
            // Audio / ovozli xabar
            const dur = a.duration ? `${a.duration}s` : '';
            preview = `<div class="mg-audio-wrap">
                <div class="mg-audio-icon">🎤</div>
                <div class="mg-audio-info">
                    <div class="mg-audio-label">${ft === 'voice' ? 'Ovozli xabar' : 'Audio'}${dur ? ' · '+dur : ''}</div>
                    <audio src="${a.file_url}" controls class="mg-audio-player" preload="metadata"></audio>
                </div>
            </div>`;
        } else {
            preview = `<a href="${a.file_url}" target="_blank" class="mg-file-link">
                <div class="mg-file-icon">${_fileIcon(mime, a.file_name)}</div>
                <div class="mg-file-name">${escapeHtml(a.file_name||'Fayl')}</div>
            </a>`;
        }

        const canDownload = !isImg && !isVid && !isVideoNote && !isVoice;
        return `
            <div class="mg-item">
                <div class="mg-preview">${preview}</div>
                <div class="mg-meta">
                    <div class="mg-uploader">${IC.user} ${byLabel}</div>
                    <div class="mg-date">${IC.calendar} ${dateStr}${sizeStr ? ' · ' + sizeStr : ''}</div>
                    ${canDownload ? `<a href="${a.file_url}" target="_blank" class="mg-download-btn">⬇️ Yuklab olish</a>` : ''}
                </div>
            </div>
        `;
    }).join('') : `<div class="mg-empty">${emptyLabel}</div>`;

    overlay.innerHTML = `
        <div class="media-sheet">
            <div class="media-sheet-header">
                <span class="media-sheet-title">${mediaLabel}${atts.length ? ' (' + atts.length + ')' : ''}</span>
                <button class="media-sheet-close" onclick="document.getElementById('media-gallery-modal').remove()">✕</button>
            </div>

            <!-- Upload area -->
            <div class="mg-upload-area">
                <div class="mg-input-row">
                    <textarea id="mg-comment-${taskId}" class="mg-comment-input"
                        placeholder="${commentPh}" rows="1" maxlength="500"
                        oninput="mgAutoResize(this)"
                        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMgComment(${taskId})}"></textarea>
                    <button class="mg-send-btn" onclick="sendMgComment(${taskId})" title="Yuborish">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                    </button>
                </div>
                <label class="mg-upload-btn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                    ${uploadLabel}
                    <input type="file" style="display:none"
                        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.zip,.rar,.pptx"
                        onchange="uploadMediaFromGallery(${taskId}, this)">
                </label>
            </div>

            <!-- Media items -->
            <div class="mg-list">${itemsHtml}</div>
        </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.querySelector('.media-sheet').classList.add('media-sheet-open'));
}

function _fileIcon(mime, name) {
    const m = (mime || '').toLowerCase();
    const ext = (name||'').split('.').pop().toLowerCase();
    if (m.includes('pdf') || ext === 'pdf') return IC.file;
    if (m.includes('word') || ['doc','docx'].includes(ext)) return IC.clipboard;
    if (m.includes('excel') || m.includes('spreadsheet') || ['xls','xlsx'].includes(ext)) return IC.chart;
    if (m.includes('powerpoint') || m.includes('presentation') || ['ppt','pptx'].includes(ext)) return IC.flag;
    if (m.includes('zip') || m.includes('rar') || ['zip','rar','7z'].includes(ext)) return IC.folder;
    return IC.attach;
}

function _formatFileSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function uploadMediaFromGallery(taskId, input) {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) { showToast('Fayl 100 MB dan kichik bo\'lsin', true); return; }

    const commentInput = document.getElementById(`mg-comment-${taskId}`);
    const comment = (commentInput?.value || '').trim();

    const fd = new FormData();
    if (comment) fd.append('comment', comment);
    fd.append('file', file);

    const uploadBtn = document.querySelector(`#media-gallery-modal .mg-upload-btn`);
    const origLabel = uploadBtn?.innerHTML;
    if (uploadBtn) uploadBtn.innerHTML = '<span style="opacity:.7">⏳ Yuklanmoqda...</span>';

    const headers = {};
    applyAuthHeaders(headers);
    try {
        const res = await fetch(`/api/tasks/${taskId}/attachments`, { method: 'POST', body: fd, headers });
        if (!res.ok) {
            let errMsg = 'Yuklab bo\'lmadi';
            try { const d = await res.json(); errMsg = d.error || errMsg; } catch(_) {}
            throw new Error(errMsg);
        }
        const commentText = (commentInput?.value || '').trim();
        showToast(commentText ? '✅ Fayl va izoh yuklandi' : '✅ Fayl yuklandi');
        if (commentInput) commentInput.value = '';
        input.value = '';
        // allTasks ni yangilaymiz
        try {
            const fresh = await apiRequest(`/tasks/${taskId}`);
            if (fresh?.task) {
                const idx = allTasks.findIndex(t => t.id === taskId);
                if (idx !== -1) allTasks[idx] = { ...allTasks[idx], ...fresh.task };
            }
        } catch(_) {}
        // Galleryni yangilaymiz
        document.getElementById('media-gallery-modal')?.remove();
        openMediaGallery(taskId);
    } catch (e) {
        showToast(e?.message || 'Yuklab bo\'lmadi', true);
        if (uploadBtn && origLabel) uploadBtn.innerHTML = origLabel;
    }
}

function mgAutoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

async function sendMgComment(taskId) {
    const input = document.getElementById(`mg-comment-${taskId}`);
    const text = (input?.value || '').trim();
    if (!text) { input?.focus(); return; }

    const btn = document.querySelector(`#media-gallery-modal .mg-send-btn`);
    if (btn) btn.disabled = true;

    try {
        const res = await apiRequest(`/tasks/${taskId}/comments`, 'POST', { content: text });
        showToast('✅ Izoh yuborildi');
        if (input) { input.value = ''; input.style.height = 'auto'; }
        // Taskni background da yangilaymiz — gallereyni yopmay
        try {
            const fresh = await apiRequest(`/tasks/${taskId}`);
            if (fresh?.task) {
                const idx = allTasks.findIndex(t => t.id === taskId);
                if (idx !== -1) allTasks[idx] = { ...allTasks[idx], ...fresh.task };
            }
        } catch(_) {}
    } catch(e) {
        showToast(e?.message || 'Yuborib bo\'lmadi', true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ============ VOICE & VIDEO RECORDING (Telegram-like) ============
let _voiceRec = null;        // { mediaRecorder, chunks, stream, taskId }
let _videoRec = null;        // { mediaRecorder, chunks, stream, taskId, overlay, startedAt }
let _videoHoldArmed = false; // 'true' if currently pressing video button

async function _uploadBlobAsComment(taskId, blob, filename, mime) {
    const file = new File([blob], filename, { type: mime });
    const commentInput = document.getElementById(`comment-input-${taskId}`);
    const comment = (commentInput?.value || '').trim();
    const fd = new FormData();
    if (comment) fd.append('comment', comment);
    fd.append('file', file);
    const headers = {};
    applyAuthHeaders(headers);
    try {
        const res = await fetch(`/api/tasks/${taskId}/attachments`, {
            method: 'POST', body: fd, headers,
        });
        if (!res.ok) throw new Error('upload failed');
        if (commentInput) commentInput.value = '';
        showToast('✅ Yuborildi');
        openTask(taskId);
    } catch (e) {
        showToast('❌ Yuborilmadi: ' + e.message, true);
    }
}

// ── Ovoz yozish (tap-to-toggle) ──
async function toggleVoiceRecord(taskId) {
    const btn = document.getElementById(`voice-btn-${taskId}`);
    if (_voiceRec) {
        // To'xtatish
        try { _voiceRec.mediaRecorder.stop(); } catch(e) {}
        return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        showToast('Brauzeringiz ovoz yozishni qo\'llab-quvvatlamaydi', true);
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus' : 'audio/webm';
        const rec = new MediaRecorder(stream, { mimeType: mime });
        const chunks = [];
        rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
        rec.onstop = async () => {
            try { stream.getTracks().forEach(t => t.stop()); } catch(e) {}
            if (btn) btn.classList.remove('recording');
            _voiceRec = null;
            if (chunks.length === 0) { showToast('Bo\'sh yozuv', true); return; }
            const blob = new Blob(chunks, { type: mime });
            const ext = mime.includes('webm') ? 'webm' : 'ogg';
            await _uploadBlobAsComment(taskId, blob, `voice_${Date.now()}.${ext}`, mime);
        };
        rec.start();
        _voiceRec = { mediaRecorder: rec, chunks, stream, taskId };
        if (btn) btn.classList.add('recording');
        if (tg) tg.HapticFeedback?.impactOccurred('medium');
        showToast('🎤 Yozilmoqda... yana bosing — yuborish');
    } catch (e) {
        showToast('Mikrofon ruxsati yo\'q', true);
    }
}

// ── Video kruzhok (hold-to-record) ──
function _videoOverlay(create = true) {
    let el = document.getElementById('video-rec-overlay');
    if (!el && create) {
        el = document.createElement('div');
        el.id = 'video-rec-overlay';
        el.className = 'video-rec-overlay';
        el.innerHTML = `
            <div class="vro-frame">
                <video id="vro-preview" autoplay muted playsinline></video>
                <div class="vro-ring"></div>
                <div class="vro-hint">⭕ Yozilmoqda... ushlab turing</div>
            </div>
        `;
        document.body.appendChild(el);
    }
    return el;
}

async function startVideoRecord(ev, taskId) {
    if (ev) ev.preventDefault();
    if (_videoRec || _videoHoldArmed) return;
    _videoHoldArmed = true;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        showToast('Brauzeringiz video yozishni qo\'llab-quvvatlamaydi', true);
        _videoHoldArmed = false;
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: { ideal: 480 }, height: { ideal: 480 } },
            audio: true,
        });
        if (!_videoHoldArmed) {
            // Tugma allaqachon qo'yib yuborilgan
            stream.getTracks().forEach(t => t.stop());
            return;
        }
        const overlay = _videoOverlay(true);
        const preview = overlay.querySelector('#vro-preview');
        preview.srcObject = stream;
        overlay.classList.add('active');

        const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
            ? 'video/webm;codecs=vp9,opus'
            : (MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')
                ? 'video/webm;codecs=vp8,opus' : 'video/webm');
        const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 800000 });
        const chunks = [];
        rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
        rec.onstop = async () => {
            try { stream.getTracks().forEach(t => t.stop()); } catch(e) {}
            const ov = _videoOverlay(false);
            if (ov) ov.classList.remove('active');
            const wasCancelled = !!_videoRec?._cancelled;
            const duration = _videoRec?.startedAt ? (Date.now() - _videoRec.startedAt) : 0;
            _videoRec = null;
            if (wasCancelled || duration < 500) {
                showToast('Yozuv bekor qilindi', true);
                return;
            }
            if (chunks.length === 0) { showToast('Bo\'sh yozuv', true); return; }
            const blob = new Blob(chunks, { type: mime });
            await _uploadBlobAsComment(taskId, blob, `video_${Date.now()}.webm`, mime);
        };
        rec.start();
        _videoRec = { mediaRecorder: rec, chunks, stream, taskId, startedAt: Date.now() };
        if (tg) tg.HapticFeedback?.impactOccurred('medium');
    } catch (e) {
        _videoHoldArmed = false;
        showToast('Kamera ruxsati yo\'q', true);
    }
}

function stopVideoRecord(ev, taskId, cancel = false) {
    if (ev) ev.preventDefault();
    if (!_videoHoldArmed) return;
    _videoHoldArmed = false;
    if (!_videoRec) return;
    if (cancel) _videoRec._cancelled = true;
    try { _videoRec.mediaRecorder.stop(); } catch(e) {}
}

async function sendCommentWithMedia(taskId, input) {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) { showToast('Fayl 100 MB dan kichik bo\'lsin', true); return; }

    const commentInput = document.getElementById(`comment-input-${taskId}`);
    const comment = (commentInput?.value || '').trim();

    const fd = new FormData();
    if (comment) fd.append('comment', comment);
    fd.append('file', file);

    const headers = {};
    applyAuthHeaders(headers);
    try {
        const res = await fetch(`/api/tasks/${taskId}/attachments`, { method: 'POST', body: fd, headers });
        if (!res.ok) throw new Error('upload failed');
        showToast('✅ Fayl va izoh yuborildi');
        if (commentInput) commentInput.value = '';
        input.value = '';
        // Taskni qayta yuklaymiz
        const fresh = await apiRequest(`/tasks/${taskId}`);
        if (fresh && fresh.task) {
            const idx = allTasks.findIndex(t => t.id === taskId);
            if (idx !== -1) allTasks[idx] = { ...allTasks[idx], ...fresh.task };
        }
        openTask(taskId);
    } catch(e) {
        showToast('Xatolik', true);
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
    applyAuthHeaders(headers);
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
    urgent: { label: 'Juda muhum', icon: IC.urgent, cls: 'urgent', pillCls: 'hero-pill-urgent' },
    high:   { label: 'Muhum',      icon: IC.high,   cls: 'high',   pillCls: 'hero-pill-high' },
    medium: { label: "O'rta",      icon: IC.medium, cls: 'medium', pillCls: 'hero-pill-medium' },
    low:    { label: 'Past',       icon: IC.low,    cls: 'low',    pillCls: 'hero-pill-low' },
};
const STATUS_LABELS_P = {
    new: 'Yangi', in_progress: 'Jarayonda', review: "Ko'rilmoqda",
    done: 'Bajarildi', overdue: 'Kechikdi', cancelled: 'Bekor',
};

async function loadPriorityTab() {
    const box = document.getElementById('priority-list');
    if (!box) return;
    box.innerHTML = `<div class="priority-loading">${IC.bolt} Yuklanmoqda...</div>`;
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
                <div class="priority-hero-title">${IC.bolt} Muhimlik darajasi</div>
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
        // Bajarilgan/bekor qilingan vazifa uchun "kechikdi" deb belgilanmaydi —
        // u allaqachon yopilgan, deadline o'tgan-o'tmaganligi ahamiyatsiz
        const urgent = isActive && diff < 0;
        const soon   = isActive && !urgent && diff < 86400000 * 2;
        let label;
        if (!isActive) {
            label = IC.calendar + ' ' + formatDate(t.deadline);
        } else if (urgent) {
            label = IC.overdue + ' ' + formatDeadline(t.deadline);
        } else if (soon) {
            label = IC.fire + ' ' + formatDeadline(t.deadline);
        } else {
            label = IC.calendar + ' ' + formatDeadline(t.deadline);
        }
        const cls = urgent ? 'pc-deadline-urgent' : (soon ? 'pc-deadline-soon' : '');
        deadlineHtml = `<span class="pc-meta-item ${cls}">${label}</span>`;
    }
    const assignees = (t.assignees || []);
    const assigneeHtml = assignees.length
        ? `<span class="pc-meta-item">${IC.user} ${assignees.map(a => escapeHtml(a.name?.split(' ')[0] || '?')).join(', ')}</span>`
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
// Bu o'zgaruvchilar dinamik — renderCalendar har chaqirilganda yangi tildagi
// nomlarni getter orqali oladi.
function _calMonths() { return Array.from({length:12}, (_,i) => _monthName(i)); }
function _calDays()   { return Array.from({length:7},  (_,i) => _dayLong(i)); }
// Backward compat — eski kod uchun
const CAL_MONTHS = new Proxy([], { get: (_, idx) => _calMonths()[idx] });
const CAL_DAYS_UZ = new Proxy([], { get: (_, idx) => _calDays()[idx] });

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

    const P_EMOJI = { urgent:IC.urgent, high:IC.high, medium:IC.medium, low:IC.low };
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
                            ? `<span class="cal-task-assignees">${IC.user} ${t.assignees.slice(0,2).map(a=>escapeHtml(a.name.split(' ')[0])).join(', ')}${t.assignees.length>2?' +'+( t.assignees.length-2):''}</span>`
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
        new: IC.new+' Yangi', in_progress: IC.progress+' Jarayonda', review: IC.review+' Ko\'rilmoqda',
        done: IC.done+' Bajarildi', overdue: IC.overdue+' Kechikdi', cancelled: IC.cancelled+' Bekor',
    };
    const PRIORITY_SHORT = {
        low: IC.low+' Past', medium: IC.medium+' O\'rta', high: IC.high+' Muhum', urgent: IC.urgent+' Juda muhum',
    };
    const statusDot = {
        new: 'dot-indigo', in_progress: 'dot-yellow', review: 'dot-purple',
        done: 'dot-green', overdue: 'dot-red', cancelled: 'dot-gray',
    };

    return history.map(h => {
        const time = formatDateTime(h.created_at);
        const uname = escapeHtml(h.user_name || '?');
        let icon = IC.pin, dotCls = 'dot-indigo', label = '', extra = '';

        switch (h.action) {
            case 'created':
                icon = IC.plus; dotCls = 'dot-indigo';
                label = `<b>${uname}</b> vazifani yaratdi`;
                break;

            case 'status_changed': {
                const nSt = (h.new_value || {}).status || '';
                icon = nSt === 'done' ? IC.done : (nSt === 'cancelled' ? IC.cancelled : IC.refresh);
                dotCls = statusDot[nSt] || 'dot-indigo';
                const oLbl = STATUS_SHORT[(h.old_value || {}).status] || '';
                const nLbl = STATUS_SHORT[nSt] || nSt;
                label = `<b>${uname}</b> umumiy statusni o'zgartirdi`;
                extra = oLbl ? `${oLbl} → <b>${nLbl}</b>` : `<b>${nLbl}</b>`;
                break;
            }

            case 'my_status_changed': {
                const mSt = (h.new_value || {}).status || '';
                icon = mSt === 'done' ? IC.done : (mSt === 'in_progress' ? IC.play : IC.refresh);
                dotCls = statusDot[mSt] || 'dot-indigo';
                const moLbl = STATUS_SHORT[(h.old_value || {}).status] || '';
                const mnLbl = STATUS_SHORT[mSt] || mSt;
                label = `<b>${uname}</b> o'z statusini o'zgartirdi`;
                extra = (moLbl ? moLbl + ' → ' : '') + `<b>${mnLbl}</b>`;
                const myCmt = (h.new_value || {}).comment;
                if (myCmt) extra += `<div class="tl-comment">${IC.comment} ${escapeHtml(myCmt)}</div>`;
                break;
            }

            case 'subtask_created': {
                icon = IC.puzzle; dotCls = 'dot-cyan';
                const stTitle = escapeHtml((h.new_value || {}).subtask_title || 'Subtask');
                const stId    = (h.new_value || {}).subtask_id;
                label = `<b>${uname}</b> subtask qo'shdi: <i>${stTitle}</i>`;
                if (stId) extra = `<button class="tl-action-btn" onclick="event.stopPropagation();closeModal();openTask(${stId})">${IC.clipboard} Ochish →</button>`;
                break;
            }

            case 'attachment_added': {
                icon = IC.attach; dotCls = 'dot-indigo';
                const fname = escapeHtml((h.new_value || {}).file_name || 'fayl');
                label = `<b>${uname}</b> fayl qo'shdi: <i>${fname}</i>`;
                break;
            }

            case 'priority_changed': {
                icon = IC.bolt; dotCls = 'dot-yellow';
                const oP = PRIORITY_SHORT[(h.old_value || {}).priority] || '';
                const nP = PRIORITY_SHORT[(h.new_value || {}).priority] || '';
                label = `<b>${uname}</b> muhimlikni o'zgartirdi`;
                extra = oP ? `${oP} → <b>${nP}</b>` : `<b>${nP}</b>`;
                break;
            }

            case 'title_changed': {
                icon = IC.edit; dotCls = 'dot-indigo';
                label = `<b>${uname}</b> sarlavhani o'zgartirdi`;
                extra = `"${escapeHtml((h.new_value || {}).title || '')}"`;
                break;
            }

            case 'comment': {
                icon = IC.comment; dotCls = 'dot-glass';
                label = `<b>${uname}</b>`;
                extra = `<div class="tl-comment">${escapeHtml(h.content || '')}</div>`;
                break;
            }

            default:
                icon = IC.pin; dotCls = 'dot-indigo';
                label = `<b>${uname}</b>: ${escapeHtml(h.action)}`;
        }

        return `
            <div class="timeline-item">
                <div class="timeline-dot ${dotCls} tl-dot-svg">${icon}</div>
                <div class="timeline-body">
                    <div class="timeline-label">${label}</div>
                    ${extra ? `<div class="tl-extra">${extra}</div>` : ''}
                    <div class="timeline-time">${time}</div>
                </div>
            </div>`;
    }).join('');
}

function switchTab(tabName) {
    // To'g'ridan-to'g'ri tab pane ni ko'rsatamiz (ghost btn click ishlamasligi mumkin)
    document.querySelectorAll('.bnav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const btn = document.querySelector(`.bnav-btn[data-tab="${tabName}"]`);
    if (btn) btn.classList.add('active');

    const pane = document.getElementById('tab-' + tabName);
    if (pane) pane.classList.add('active');

    const tabTitles = { tasks: 'Vazifalar', calendar: 'Kalendar', create: 'Yangi vazifa', kanban: 'Kanban', stats: 'Statistika', hujjatlar: 'Hujjatlarim' };
    const hTitle = document.getElementById('header-title');
    if (hTitle) {
        if (tabName === 'create' && _subtaskParentId) hTitle.textContent = 'Sub-task yaratish';
        else hTitle.textContent = tabTitles[tabName] || 'TaskBot';
    }

    _navStack.length = 0;
    document.getElementById('back-btn')?.classList.add('hidden');
    document.getElementById('hamburger-btn')?.classList.remove('hidden');

    const qs = document.getElementById('quick-stats');
    if (qs) qs.classList.toggle('hidden', tabName !== 'tasks');

    if (tabName === 'kanban') { renderKanbanMemberBar(); renderKanban(); }
    if (tabName === 'calendar') renderCalendar();
    if (tabName !== 'create' && _subtaskParentId) {
        _subtaskParentId = null; _subtaskParentTitle = null; _updateSubtaskBanner();
    }
    if (tg) tg.HapticFeedback?.impactOccurred('light');
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
        // Boshlash — in_progress ga o'tkazish
        try {
            const r = await apiRequest(`/tasks/${taskId}/start`, 'POST');
            if (r.ok && r.status === 'in_progress') {
                tg?.HapticFeedback?.notificationOccurred('success');
                showToast('▶️ Taskni boshladingiz!');
                await openTask(taskId);
            }
        } catch (e) {
            showToast('❌ Xato: ' + (e.message || e), true);
        }
    } else if (myStatus === 'in_progress') {
        // Bajarildi — changeMyStatus orqali (ishonchli, xatoni ko'rsatadi)
        changeMyStatus(taskId, 'done');
    } else {
        showToast('✓ Bu task allaqachon tugagan');
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
                <h3>${IC.done} Taskni tugatish</h3>
                <button class="wf-modal-close" onclick="closeTaskCompleteModal()">×</button>
            </div>
            <div class="wf-modal-body">
                <label class="wf-lbl">${IC.comment} Nimani bajardingiz? (ixtiyoriy)</label>
                <textarea id="task-comment-input" class="wf-textarea" rows="3"
                          placeholder="Qisqacha yozing..."></textarea>
            </div>
            <div class="wf-modal-foot">
                <button class="wf-btn-secondary" onclick="closeTaskCompleteModal()">Bekor</button>
                <button class="wf-btn-primary" onclick="submitTaskComplete(${taskId})">${IC.done} Saqlash</button>
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


// ================================================================
// KANBAN MEMBER FILTER
// ================================================================

let _kanbanMemberId = null;   // null = show all

function renderKanbanMemberBar() {
    const bar = document.getElementById('kanban-member-bar');
    if (!bar) return;

    // Collect unique members from allTasks (assignees)
    const memberMap = {};  // id → {id, name, taskCount}
    const source = allTasks && allTasks.length > 0 ? allTasks : [];
    source.forEach(t => {
        if (t.assignees && t.assignees.length) {
            t.assignees.forEach(a => {
                if (!memberMap[a.id]) {
                    memberMap[a.id] = { id: a.id, name: a.name, taskCount: 0 };
                }
                if (!['done', 'cancelled'].includes(t.status)) {
                    memberMap[a.id].taskCount++;
                }
            });
        }
        // Also include responsible_name if present
        if (t.responsible_user_id && t.responsible_name && !memberMap[t.responsible_user_id]) {
            memberMap[t.responsible_user_id] = {
                id: t.responsible_user_id,
                name: t.responsible_name,
                taskCount: 0,
            };
        }
    });

    const members = Object.values(memberMap).sort((a, b) => b.taskCount - a.taskCount);

    bar.style.display = 'flex';

    const allActive = _kanbanMemberId === null;
    const myId = window._myUserId;
    const myActive = myId && _kanbanMemberId === myId;
    let html = `
        <div class="kmb-chip ${allActive ? 'active' : ''}" onclick="filterKanbanByMember(null)">
            <div class="kmb-avatar all-icon">${IC.team}</div>
            <span class="kmb-name">Hammasi</span>
        </div>
    `;

    if (myId) {
        html += `
            <div class="kmb-chip kmb-chip-me ${myActive ? 'active' : ''}" onclick="filterKanbanByMember(${myId})">
                <div class="kmb-avatar">🙋</div>
                <span class="kmb-name">Mening</span>
            </div>
        `;
    }

    members.filter(m => m.id !== myId).forEach(m => {
        const initial = (m.name || '?').charAt(0).toUpperCase();
        const isActive = _kanbanMemberId === m.id;
        const badge = m.taskCount > 0 ? `<span class="kmb-badge">${m.taskCount}</span>` : '';
        html += `
            <div class="kmb-chip ${isActive ? 'active' : ''}" onclick="filterKanbanByMember(${m.id})">
                <div class="kmb-avatar">${escapeHtml(initial)}${badge}</div>
                <span class="kmb-name">${escapeHtml(m.name.split(' ')[0])}</span>
            </div>
        `;
    });

    bar.innerHTML = html;
}

function filterKanbanByMember(memberId) {
    _kanbanMemberId = memberId;
    if (tg) tg.HapticFeedback?.selectionChanged();
    renderKanbanMemberBar();
    renderKanban();
}

// ================================================================
// KANBAN BOARD
// ================================================================

function renderKanban() {
    const cols = ['new', 'in_progress', 'review', 'done'];
    const pLabels = new Proxy({}, { get: (_, p) => getPriorityLabel(p) });
    const pClass  = { low: 'prio-low', medium: 'prio-medium', high: 'prio-high', urgent: 'prio-urgent' };

    // Clear columns
    cols.forEach(c => {
        const el = document.getElementById('kanban-cards-' + c);
        if (el) el.innerHTML = '<div class="kanban-empty"><span class="kanban-empty-icon">⏳</span><span>Yuklanmoqda...</span></div>';
        _setKanbanCount(c, 0);
    });

    const source = allTasks && allTasks.length > 0 ? allTasks : null;

    function _fill(tasks) {
        let filtered = tasks;
        if (_kanbanMemberId !== null) {
            filtered = tasks.filter(t =>
                (t.assignees && t.assignees.some(a => a.id === _kanbanMemberId)) ||
                t.responsible_user_id === _kanbanMemberId
            );
        }

        const groups = { new: [], in_progress: [], review: [], done: [] };
        // Guruhlik/tayinlangan task uchun my_status bo'yicha joylashtir,
        // shaxsiy task uchun umumiy status bo'yicha
        filtered.forEach(t => {
            const col = (t.my_status) ? t.my_status : t.status;
            if (groups[col]) groups[col].push(t);
        });

        cols.forEach(col => {
            const el  = document.getElementById('kanban-cards-' + col);
            const list = groups[col] || [];
            _setKanbanCount(col, list.length);
            if (!el) return;

            if (!list.length) {
                const emptyMsgs = { new:'Yangi vazifa yo\'q', in_progress:'Jarayonda yo\'q', review:'Ko\'rib chiqilmoqda yo\'q', done:'Bajarilgan yo\'q' };
                const emptyIcons = { new:IC.circle, in_progress:IC.clock, review:IC.review, done:IC.done };
                el.innerHTML = `<div class="kanban-empty"><span class="kanban-empty-icon">${emptyIcons[col]||IC.circle}</span><span>${emptyMsgs[col]||'Bo\'sh'}</span></div>`;
                return;
            }

            el.innerHTML = list.map(t => {
                const isUrgentDl = t.deadline && (new Date(t.deadline) - Date.now()) < 3600000 && t.status !== 'done';
                const dlClass = isUrgentDl ? 'kanban-card-dl kanban-card-dl-urgent' : 'kanban-card-dl';
                const dl   = t.deadline ? `<span class="${dlClass}">${IC.clock} ${formatDateShort(t.deadline)}</span>` : '';
                const resp = t.responsible_name
                    ? `<div class="kanban-card-resp">${IC.star} ${escapeHtml(t.responsible_name.split(' ')[0])}</div>` : '';
                const assignees = (t.assignees || []).filter(a => !t.responsible_user_id || a.id !== t.responsible_user_id);
                const asgn = assignees.length
                    ? `<div class="kanban-card-resp" style="color:var(--text2)">${IC.user} ${assignees.slice(0,2).map(a=>escapeHtml(a.name.split(' ')[0])).join(', ')}${assignees.length>2?' +'+( assignees.length-2):''}</div>` : '';
                const subs = (t.subtasks_count||0) > 0 ? `<div class="kanban-card-subtasks">${IC.folder} ${t.subtasks_count} sub-task</div>` : '';
                return `
                    <div class="kanban-card" data-priority="${t.priority}" data-task-id="${t.id}"
                         draggable="true"
                         onclick="openTask(${t.id})"
                         ondragstart="_kbDragStart(event,${t.id})"
                         ontouchstart="_kbTouchStart(event,${t.id})"
                         ontouchmove="_kbTouchMove(event)"
                         ontouchend="_kbTouchEnd(event)">
                        <div class="kanban-drag-handle">⠿</div>
                        <div class="kanban-card-title">${escapeHtml(t.title.slice(0, 70))}</div>
                        <div class="kanban-card-meta">
                            <span class="kanban-card-prio ${pClass[t.priority]||''}">${pLabels[t.priority]||t.priority}</span>
                            ${dl}
                        </div>
                        ${resp}${asgn}${subs}
                    </div>`;
            }).join('');
        });
    }

    if (source) {
        _fill(source);
    } else {
        loadTasksForKanban().then(_fill).catch(() => {
            cols.forEach(c => {
                const el = document.getElementById('kanban-cards-' + c);
                if (el) el.innerHTML = '<div class="kanban-empty"><span class="kanban-empty-icon">❌</span><span>Yuklab bo\'lmadi</span></div>';
            });
        });
    }

    // Setup scroll→tab sync
    _kanbanInitScrollSync();
}

function _setKanbanCount(col, n) {
    ['', '2'].forEach(sfx => {
        const el = document.getElementById('kanban-count-' + col + sfx);
        if (el) el.textContent = n;
    });
}

// Scroll to a specific column by clicking its tab
function kanbanScrollTo(col) {
    const board = document.getElementById('kanban-board');
    const target = document.getElementById('kanban-' + col);
    if (!board || !target) return;
    board.scrollTo({ left: target.offsetLeft, behavior: 'smooth' });
    _kanbanSetActiveTab(col);
}

function _kanbanSetActiveTab(col) {
    document.querySelectorAll('#kanban-col-tabs .kct-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.col === col);
    });
}

let _kanbanScrollTimer = null;
function _kanbanInitScrollSync() {
    const board = document.getElementById('kanban-board');
    if (!board || board._syncBound) return;
    board._syncBound = true;
    board.addEventListener('scroll', () => {
        clearTimeout(_kanbanScrollTimer);
        _kanbanScrollTimer = setTimeout(() => {
            const cols = ['new', 'in_progress', 'review', 'done'];
            const boardLeft = board.getBoundingClientRect().left;
            let closest = cols[0], minDist = Infinity;
            cols.forEach(c => {
                const el = document.getElementById('kanban-' + c);
                if (!el) return;
                const dist = Math.abs(el.getBoundingClientRect().left - boardLeft);
                if (dist < minDist) { minDist = dist; closest = c; }
            });
            _kanbanSetActiveTab(closest);
        }, 80);
    }, { passive: true });
}

async function loadTasksForKanban() {
    const ws = currentWorkspaceId || 'personal';
    const data = await apiRequest(`/tasks?company_id=${ws}`);
    return data.tasks || [];
}

function formatDateShort(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
    } catch { return ''; }
}

// ================================================================
// KANBAN DRAG AND DROP
// ================================================================

let _kbDragTaskId = null;
let _kbDragEl = null;
let _kbDragClone = null;
let _kbDragStartX = 0;
let _kbDragStartY = 0;
let _kbLastCol = null;

// — Mouse / HTML5 drag —
function _kbDragStart(e, taskId) {
    _kbDragTaskId = taskId;
    _kbDragEl = e.currentTarget;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(taskId));
    setTimeout(() => { if (_kbDragEl) _kbDragEl.classList.add('kb-dragging'); }, 0);
}

function _kbDragOver(e, col) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (_kbLastCol !== col) {
        if (_kbLastCol) document.getElementById('kanban-' + _kbLastCol)?.classList.remove('kb-drop-target');
        _kbLastCol = col;
        document.getElementById('kanban-' + col)?.classList.add('kb-drop-target');
    }
}

function _kbDragLeave(e) {
    const col = e.currentTarget?.id?.replace('kanban-', '');
    if (col) document.getElementById('kanban-' + col)?.classList.remove('kb-drop-target');
    if (_kbLastCol === col) _kbLastCol = null;
}

async function _kbDrop(e, col) {
    e.preventDefault();
    const cols = ['new','in_progress','review','done'];
    cols.forEach(c => document.getElementById('kanban-' + c)?.classList.remove('kb-drop-target'));
    if (_kbDragEl) _kbDragEl.classList.remove('kb-dragging');
    const taskId = _kbDragTaskId || parseInt(e.dataTransfer.getData('text/plain'));
    _kbDragTaskId = null;
    _kbDragEl = null;
    _kbLastCol = null;
    if (!taskId || !col) return;

    // Find task in allTasks
    const task = allTasks.find(t => t.id === taskId);
    if (!task) return;

    // Guruhlik/tayinlangan vazifami? my_status bor bo'lsa — faqat o'z statusini o'zgartir
    const isAssigned = task.my_status != null;
    const currentCol = isAssigned ? task.my_status : task.status;
    if (currentCol === col) return;

    // Optimistic update
    if (isAssigned) {
        task.my_status = col;
    } else {
        task.status = col;
    }
    renderKanban();
    if (tg) tg.HapticFeedback?.impactOccurred('medium');

    try {
        if (isAssigned) {
            // Faqat mening statusimni o'zgartir
            await apiRequest(`/tasks/${taskId}/my-status`, 'PATCH', { status: col });
        } else {
            // Shaxsiy vazifa — umumiy statusni o'zgartir
            await apiRequest(`/tasks/${taskId}/status`, 'PATCH', { status: col });
        }
        showToast(`✅ Status o'zgartirildi`);
    } catch (err) {
        showToast('❌ Xatolik', true);
        // Revert
        try {
            const d = await apiRequest(`/tasks/${taskId}`);
            const idx = allTasks.findIndex(t => t.id === taskId);
            if (idx >= 0 && d.task) allTasks[idx] = d.task;
        } catch {}
        renderKanban();
    }
}

// — Touch drag —
function _kbTouchStart(e, taskId) {
    const touch = e.touches[0];
    _kbDragTaskId = taskId;
    _kbDragEl = e.currentTarget;
    _kbDragStartX = touch.clientX;
    _kbDragStartY = touch.clientY;

    // Clone for visual drag
    _kbDragClone = _kbDragEl.cloneNode(true);
    _kbDragClone.style.cssText = `
        position:fixed; z-index:9999; opacity:0.92; pointer-events:none;
        width:${_kbDragEl.offsetWidth}px;
        box-shadow:0 8px 32px rgba(0,0,0,0.5);
        border-radius:14px; transform:rotate(2deg) scale(1.04);
        left:${_kbDragEl.getBoundingClientRect().left}px;
        top:${_kbDragEl.getBoundingClientRect().top}px;
        transition:none;
    `;
    document.body.appendChild(_kbDragClone);
    _kbDragEl.classList.add('kb-dragging');
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function _kbTouchMove(e) {
    if (!_kbDragClone) return;
    e.preventDefault();
    const touch = e.touches[0];
    const dx = touch.clientX - _kbDragStartX;
    const dy = touch.clientY - _kbDragStartY;
    const orig = _kbDragEl.getBoundingClientRect();
    _kbDragClone.style.left = (orig.left + dx) + 'px';
    _kbDragClone.style.top  = (orig.top  + dy) + 'px';

    // Highlight column under finger
    const cols = ['new','in_progress','review','done'];
    const underEl = document.elementFromPoint(touch.clientX, touch.clientY);
    const targetCol = cols.find(c => document.getElementById('kanban-' + c)?.contains(underEl));
    cols.forEach(c => document.getElementById('kanban-' + c)?.classList.remove('kb-drop-target'));
    if (targetCol) document.getElementById('kanban-' + targetCol)?.classList.add('kb-drop-target');
}

async function _kbTouchEnd(e) {
    if (!_kbDragClone) return;
    const touch = e.changedTouches[0];
    _kbDragClone.remove();
    _kbDragClone = null;
    if (_kbDragEl) _kbDragEl.classList.remove('kb-dragging');

    const cols = ['new','in_progress','review','done'];
    const underEl = document.elementFromPoint(touch.clientX, touch.clientY);
    const targetCol = cols.find(c => document.getElementById('kanban-' + c)?.contains(underEl));
    cols.forEach(c => document.getElementById('kanban-' + c)?.classList.remove('kb-drop-target'));

    const taskId = _kbDragTaskId;
    _kbDragTaskId = null;
    _kbDragEl = null;

    if (!targetCol || !taskId) return;
    const task = allTasks.find(t => t.id === taskId);
    if (!task) return;

    const isAssigned = task.my_status != null;
    const currentCol = isAssigned ? task.my_status : task.status;
    if (currentCol === targetCol) return;

    if (isAssigned) {
        task.my_status = targetCol;
    } else {
        task.status = targetCol;
    }
    renderKanban();
    if (tg) tg.HapticFeedback?.impactOccurred('medium');

    try {
        if (isAssigned) {
            await apiRequest(`/tasks/${taskId}/my-status`, 'PATCH', { status: targetCol });
        } else {
            await apiRequest(`/tasks/${taskId}/status`, 'PATCH', { status: targetCol });
        }
        showToast(`✅ Status o'zgartirildi`);
    } catch (err) {
        showToast('❌ Xatolik', true);
        try {
            const d = await apiRequest(`/tasks/${taskId}`);
            const idx = allTasks.findIndex(t => t.id === taskId);
            if (idx >= 0 && d.task) allTasks[idx] = d.task;
        } catch {}
        renderKanban();
    }
}

// ================================================================
// KANBAN INLINE TOGGLE (Tasks tab ichida)
// ================================================================

let _kanbanInlineVisible = false;

function toggleKanbanView() {
    _kanbanInlineVisible = !_kanbanInlineVisible;
    const wrap = document.getElementById('task-kanban-inline');
    const list = document.getElementById('task-list');
    const empty = document.getElementById('empty-tasks');
    const btn   = document.getElementById('btn-toggle-kanban');

    if (_kanbanInlineVisible) {
        wrap && wrap.classList.remove('hidden');
        list && list.classList.add('hidden');
        empty && empty.classList.add('hidden');
        btn && btn.classList.add('active');
        _renderKanbanInline();
    } else {
        wrap && wrap.classList.add('hidden');
        list && list.classList.remove('hidden');
        btn && btn.classList.remove('active');
        applyFilter(); // ro'yxatni qayta ko'rsatish
    }
}

function _renderKanbanInline() {
    const cols = ['new', 'in_progress', 'review', 'done'];
    const pClass = { low: 'prio-low', medium: 'prio-medium', high: 'prio-high', urgent: 'prio-urgent' };

    function fill(tasks) {
        const groups = { new: [], in_progress: [], review: [], done: [] };
        tasks.forEach(t => { if (groups[t.status]) groups[t.status].push(t); });
        cols.forEach(col => {
            const el  = document.getElementById('ki-cards-' + col);
            const cnt = document.getElementById('ki-count-' + col);
            if (!el) return;
            const list = groups[col] || [];
            if (cnt) cnt.textContent = list.length;
            if (!list.length) { el.innerHTML = '<div class="ki-empty">Bo\'sh</div>'; return; }
            el.innerHTML = list.map(t => `
                <div class="kanban-card" onclick="openTask(${t.id})">
                    <div class="kanban-card-title">${escapeHtml(t.title.slice(0, 55))}</div>
                    <div class="kanban-card-meta">
                        <span class="kanban-card-prio ${pClass[t.priority] || ''}">${t.priority}</span>
                        ${t.deadline ? `<span class="kanban-card-dl">${IC.clock} ${formatDateShort(t.deadline)}</span>` : ''}
                    </div>
                    ${t.responsible_name ? `<div class="kanban-card-resp">⭐ ${escapeHtml(t.responsible_name)}</div>` : ''}
                </div>
            `).join('');
        });
    }

    if (allTasks && allTasks.length > 0) { fill(allTasks); return; }
    loadTasksForKanban().then(fill).catch(() => {
        cols.forEach(c => { const el = document.getElementById('ki-cards-' + c); if (el) el.innerHTML = '<div class="ki-empty" style="color:red">Xato</div>'; });
    });
}

// ================================================================
// SUBTASK INLINE CREATE
// ================================================================

async function openSubtaskCreate(parentTaskId) { openSubtaskModal(parentTaskId); }

// Sub-task modal: selected assignee IDs
let _stAssigneeIds = [];

async function openSubtaskModal(parentTaskId) {
    const existing = document.getElementById('subtask-full-modal');
    if (existing) existing.remove();

    _stAssigneeIds = [];

    // Use already-loaded companyMembers; fetch if empty and workspace is set
    let members = companyMembers.slice();
    if (!members.length && currentWorkspaceId && currentWorkspaceId !== 'all' && currentWorkspaceId !== 'personal') {
        try {
            const data = await apiRequest(`/companies/${currentWorkspaceId}/members`);
            members = data.members || [];
        } catch(e) {}
    }
    // Pre-select self
    const selfM = members.find(m => m.is_self);
    if (selfM) _stAssigneeIds.push(selfM.id);

    const pLow    = tr('app.priority.low')    || (IC.low    + ' Past');
    const pMed    = tr('app.priority.medium') || (IC.medium + " O'rta");
    const pHigh   = tr('app.priority.high')   || (IC.high   + ' Muhum');
    const pUrgent = tr('app.priority.urgent') || (IC.urgent + ' Juda muhum');

    const membersHtml = members.length ? members.map(m => {
        const sel = _stAssigneeIds.includes(m.id);
        const init = (m.name || '?')[0].toUpperCase();
        return `<div class="assignee-chip ${sel ? 'selected' : ''}" id="stchip-${m.id}" onclick="_stToggleAssignee(${m.id},this)">
            <span class="assignee-avatar">${escapeHtml(init)}</span>
            <span class="assignee-name">${IC.user} ${escapeHtml(m.name)}${m.is_self?' (siz)':''}</span>
            <span class="assignee-check">${sel ? '✓' : ''}</span>
        </div>`;
    }).join('') : `<div class="form-hint" style="margin:0">Shaxsiy workspace — ijrochi tanlanmaydi</div>`;

    const overlay = document.createElement('div');
    overlay.id = 'subtask-full-modal';
    overlay.className = 'st-modal-overlay';
    overlay.innerHTML = `
        <div class="st-modal-sheet">
            <div class="st-modal-header">
                <span class="st-modal-title">📂 Sub-task yaratish</span>
                <button class="st-modal-close" onclick="document.getElementById('subtask-full-modal').remove()">✕</button>
            </div>

            <div class="form-group" style="margin-bottom:14px">
                <label class="form-label">Nomi *</label>
                <input id="st-title" type="text" placeholder="Sub-task nomi..." maxlength="200" class="st-input">
            </div>

            <div class="form-group" style="margin-bottom:14px">
                <label class="form-label">Tavsif</label>
                <textarea id="st-desc" rows="2" placeholder="Ixtiyoriy..." class="st-textarea"></textarea>
            </div>

            <div class="form-group" style="margin-bottom:14px">
                <label class="form-label">Muhimlik</label>
                <div class="priority-selector" id="st-prio-btns">
                    <button class="priority-btn" data-prio="low" onclick="_stPrio(this)">${pLow}</button>
                    <button class="priority-btn selected" data-prio="medium" onclick="_stPrio(this)">${pMed}</button>
                    <button class="priority-btn" data-prio="high" onclick="_stPrio(this)">${pHigh}</button>
                    <button class="priority-btn" data-prio="urgent" onclick="_stPrio(this)">${pUrgent}</button>
                </div>
            </div>

            <div class="form-group" style="margin-bottom:14px">
                <label class="form-label">Deadline</label>
                <div style="display:flex;gap:8px;align-items:center">
                    <button class="dl-picker-btn" id="st-dl-btn" onclick="_stOpenDeadline()" style="flex:1;text-align:left">
                        ${IC.calendar} <span id="st-dl-label">Sana tanlang...</span>
                    </button>
                    <button onclick="_stClearDeadline()" style="background:none;border:none;color:var(--text3);font-size:20px;cursor:pointer;padding:4px">✕</button>
                </div>
                <input type="hidden" id="st-deadline">
            </div>

            ${members.length ? `<div class="form-group" style="margin-bottom:14px">
                <label class="form-label">👥 Kuzatuvchilar</label>
                <div id="st-assignees-list">${membersHtml}</div>
            </div>` : ''}

            <button onclick="_submitSubtaskFull(${parentTaskId})" class="btn-create" style="margin-top:8px">
                <span>✅ Sub-task yaratish</span>
            </button>
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    setTimeout(() => document.getElementById('st-title')?.focus(), 100);
}

function _stToggleAssignee(uid, chip) {
    const idx = _stAssigneeIds.indexOf(uid);
    if (idx >= 0) {
        _stAssigneeIds.splice(idx, 1);
        chip.classList.remove('selected');
        chip.querySelector('.assignee-check').textContent = '';
    } else {
        _stAssigneeIds.push(uid);
        chip.classList.add('selected');
        chip.querySelector('.assignee-check').textContent = '✓';
    }
    if (tg) tg.HapticFeedback?.selectionChanged();
}

// Subtask uchun deadline picker (asosiy pickerni subtask kontekstiga bog'laymiz)
let _stDeadlineActive = false;
function _stOpenDeadline() {
    _stDeadlineActive = true;
    // Asosiy picker ni ochib, callback ni override qilamiz
    openDeadlinePicker();
    // confirmDeadlinePicker ni patch qilamiz
    window._originalConfirmDl = window.confirmDeadlinePicker;
    window.confirmDeadlinePicker = function() {
        // Qiymatni st-deadline ga joylashtiramiz
        const y = _dlState.y, mo = _dlState.m, d = _dlState.d;
        const h = _dlState.hour, mi = _dlState.minute;
        const dt = new Date(y, mo, d, h, mi);
        const iso = dt.toISOString();
        document.getElementById('st-deadline').value = iso;
        const label = `${d.toString().padStart(2,'0')}.${(mo+1).toString().padStart(2,'0')}.${y} ${h.toString().padStart(2,'0')}:${mi.toString().padStart(2,'0')}`;
        const lblEl = document.getElementById('st-dl-label');
        if (lblEl) lblEl.textContent = label;
        // Pickerni yopamiz
        document.getElementById('dl-sheet')?.classList.add('hidden');
        // Restore
        window.confirmDeadlinePicker = window._originalConfirmDl;
        _stDeadlineActive = false;
    };
}
function _stClearDeadline() {
    document.getElementById('st-deadline').value = '';
    const lblEl = document.getElementById('st-dl-label');
    if (lblEl) lblEl.textContent = 'Tanlang...';
}

function _stPrio(btn) {
    document.querySelectorAll('#st-prio-btns .priority-btn, #st-prio-btns .st-prio').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
}

async function _submitSubtaskFull(parentTaskId) {
    const title = (document.getElementById('st-title')?.value || '').trim();
    if (title.length < 2) { showToast('❗ Nom kamida 2 belgi', true); return; }

    const desc     = (document.getElementById('st-desc')?.value || '').trim() || null;
    const priority = document.querySelector('#st-prio-btns .selected')?.dataset?.prio || 'medium';
    const dlRaw    = document.getElementById('st-deadline')?.value;
    const deadline = dlRaw || null;
    const assignee_ids = _stAssigneeIds.slice();

    const btn = document.querySelector('#subtask-full-modal button:last-child');
    if (btn) { btn.disabled = true; btn.textContent = 'Saqlanmoqda...'; }

    try {
        const r = await apiRequest('/tasks', 'POST', {
            title, description: desc, priority,
            deadline, parent_id: parentTaskId,
            assignee_ids,
        });
        if (r && r.ok) {
            showToast('✅ Sub-task yaratildi!');
            document.getElementById('subtask-full-modal')?.remove();
            await openTask(parentTaskId);
            // allTasks ni yangilaymiz
            await loadTasks();
        } else {
            showToast('❌ ' + (r?.error || 'Xato'), true);
            if (btn) { btn.disabled = false; btn.textContent = '✅ Yaratish'; }
        }
    } catch (e) {
        showToast('❌ ' + (e.message || 'Server xatosi'), true);
        if (btn) { btn.disabled = false; btn.textContent = '✅ Yaratish'; }
    }
}

async function submitSubtask(parentTaskId) {
    // Legacy: inline form fallback
    const input = document.getElementById('subtask-title-input');
    const title = input?.value?.trim();
    if (!title) return;

    try {
        const r = await apiRequest('/tasks', 'POST', {
            title, parent_id: parentTaskId, priority: 'medium', assignee_ids: [],
        });
        if (r && r.ok) {
            showToast('✅ Sub-task yaratildi!');
            document.getElementById('subtask-create-form')?.remove();
            await openTask(parentTaskId);
        } else {
            showToast('❌ ' + (r?.error || 'Xato'), true);
        }
    } catch (e) {
        showToast('❌ ' + (e.message || e), true);
    }
}

// ═══════════════════════════════════════════════════════════
//  SUBTASK TYPE PICKER  (v80)
// ═══════════════════════════════════════════════════════════

/** Show "Odiy task" vs "Ketma-ketlik" bottom sheet before creating sub-task */
function openSubtaskTypePicker(parentTaskId) {
    const task = allTasks.find(t => t.id === parentTaskId);
    const title = task?.title || `#${parentTaskId}`;

    document.getElementById('stp-overlay')?.remove();

    const el = document.createElement('div');
    el.id  = 'stp-overlay';
    el.className = 'stp-overlay';
    el.innerHTML = `
        <div class="stp-sheet">
            <div class="stp-handle"></div>
            <div class="stp-title">📂 Sub-task turini tanlang</div>
            <div class="stp-parent-ref">↳ ${escapeHtml(title.slice(0,55))}</div>

            <button class="stp-option" onclick="_launchSubtaskCreate(${parentTaskId},'regular')">
                <span class="stp-opt-icon">📋</span>
                <span class="stp-opt-info">
                    <span class="stp-opt-name">Oddiy task</span>
                    <span class="stp-opt-desc">Oddiy sub-vazifa yaratish</span>
                </span>
                <span class="stp-opt-arrow">›</span>
            </button>

            <button class="stp-option" onclick="_launchSubtaskCreate(${parentTaskId},'workflow')">
                <span class="stp-opt-icon">🔗</span>
                <span class="stp-opt-info">
                    <span class="stp-opt-name">Ketma-ketlik</span>
                    <span class="stp-opt-desc">Qadamli workflow sub-vazifa</span>
                </span>
                <span class="stp-opt-arrow">›</span>
            </button>

            <button class="stp-cancel" onclick="document.getElementById('stp-overlay')?.remove()">Bekor qilish</button>
        </div>
    `;
    document.body.appendChild(el);
    el.addEventListener('click', e => { if (e.target === el) el.remove(); });
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

/** Navigate to create tab with chosen type and parent context */
function _launchSubtaskCreate(parentTaskId, type) {
    document.getElementById('stp-overlay')?.remove();

    _subtaskParentId    = parentTaskId;
    const task = allTasks.find(t => t.id === parentTaskId);
    _subtaskParentTitle = task?.title || `#${parentTaskId}`;

    // Close the task detail modal FIRST (it's a fixed overlay — switching tabs doesn't hide it)
    closeModal();

    // Switch to create tab
    document.querySelector('.bnav-btn[data-tab="create"]')?.click();

    // Select task type
    selectTaskType(type);

    // Show parent banner
    _updateSubtaskBanner();

    if (tg) tg.HapticFeedback?.impactOccurred('medium');
}

/** Update the parent banner on create form */
function _updateSubtaskBanner() {
    const banner = document.getElementById('subtask-parent-banner');
    const label  = document.getElementById('subtask-parent-label');
    const titleEl = document.getElementById('create-form-title');
    if (!banner) return;
    if (_subtaskParentId) {
        banner.classList.remove('hidden');
        if (label) label.textContent = 'Sub-task: ' + (_subtaskParentTitle || `#${_subtaskParentId}`).slice(0,55);
        if (titleEl) titleEl.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 3v12"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9v1a2 2 0 01-2 2H6"/></svg> Sub-task yaratish`;
    } else {
        banner.classList.add('hidden');
        if (titleEl) titleEl.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Yangi vazifa`;
    }
}

/** Clear sub-task mode (called by ✕ button on banner) */
function _clearSubtaskMode() {
    _subtaskParentId    = null;
    _subtaskParentTitle = null;
    _updateSubtaskBanner();
    selectTaskType('regular');
}

// ── Navigation stack for back button ────────────────────────────────────────
const _navStack = [];

function pushNav(fn) {
    _navStack.push(fn);
    document.getElementById('back-btn')?.classList.remove('hidden');
    document.getElementById('hamburger-btn')?.classList.add('hidden');
}

function goBack() {
    if (_navStack.length > 0) {
        const fn = _navStack.pop();
        fn();
    }
    if (_navStack.length === 0) {
        document.getElementById('back-btn')?.classList.add('hidden');
        document.getElementById('hamburger-btn')?.classList.remove('hidden');
    }
}

// ================================================================
// SIDEBAR (Hamburger Menu)
// ================================================================

function openSidebar() {
    const sb = document.getElementById('sidebar');
    const ov = document.getElementById('sidebar-overlay');
    if (!sb || !ov) return;
    ov.classList.remove('hidden');
    sb.classList.remove('hidden');
    setTimeout(() => sb.classList.add('open'), 10);
    document.getElementById('hamburger-btn')?.classList.add('is-open');
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    // Sync profile info
    const sbName = document.getElementById('sb-name');
    const sbSub = document.getElementById('sb-sub');
    const sbAv = document.getElementById('sb-avatar');
    if (sbName) sbName.textContent = window._currentUserName || 'Foydalanuvchi';
    if (sbAv) {
        const mainAv = document.getElementById('user-avatar');
        if (mainAv) {
            sbAv.style.backgroundImage = mainAv.style.backgroundImage;
            sbAv.style.backgroundSize = 'cover';
            sbAv.style.backgroundPosition = 'center';
            const txt = mainAv.textContent;
            sbAv.textContent = mainAv.style.backgroundImage ? '' : txt;
        }
    }
    if (sbSub && tg?.initDataUnsafe?.user?.username) {
        sbSub.textContent = '@' + tg.initDataUnsafe.user.username;
    }
}

function closeSidebar() {
    const sb = document.getElementById('sidebar');
    const ov = document.getElementById('sidebar-overlay');
    if (!sb) return;
    sb.classList.remove('open');
    document.getElementById('hamburger-btn')?.classList.remove('is-open');
    setTimeout(() => {
        ov?.classList.add('hidden');
        sb.classList.add('hidden');
    }, 300);
}

// ================================================================
// COMPANIES PANEL
// ================================================================

let _companiesCache = null;

async function openTeamsPanel() {
    openCompaniesPanel();
}

async function openCompaniesPanel() {
    closeSidebar();
    const panel = document.getElementById('companies-panel');
    const list = document.getElementById('companies-list');
    if (!panel) return;
    panel.classList.remove('hidden');
    setTimeout(() => panel.classList.add('open'), 10);
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    list.innerHTML = '<div class="sp-loading">⏳ Yuklanmoqda...</div>';
    try {
        const data = await apiRequest('/workspaces');
        const workspaces = (data.workspaces || []).filter(w => w.id !== 'personal');
        _companiesCache = workspaces;

        // Also try to load telegram groups
        let groups = [];
        try {
            const gData = await apiRequest('/groups');
            groups = gData.groups || [];
        } catch (e) {
            // /api/groups may not exist yet — ignore
        }

        // Update sidebar badge
        const badge = document.getElementById('sb-companies-count');
        if (badge) badge.textContent = (workspaces.length + groups.length) || '';

        if (!workspaces.length && !groups.length) {
            list.innerHTML = '<div class="sp-loading">Hech qanday jamoa yo\'q</div>';
            return;
        }

        let html = '';

        // Bot jamoalari section
        if (workspaces.length) {
            html += `<div class="cmp-action-title" style="margin-bottom:8px">${IC.building} Bot jamoalari</div>`;
            html += workspaces.map(w => {
                const isOwner = w.is_owner;
                const isAdmin = w.is_admin || isOwner;
                const roleLabel = isOwner ? IC.crown+' Owner' : (isAdmin ? IC.shield+' Admin' : IC.user+' A\'zo');
                const roleClass = isOwner ? 'owner' : '';
                return `
                    <div class="company-card" onclick="openCompanyDetail(${w.id},'${escapeHtml(w.name)}',${isAdmin})">
                        <div class="company-card-row">
                            <span class="company-card-name">${IC.building} ${escapeHtml(w.name)}</span>
                            <span class="company-card-role ${roleClass}">${roleLabel}</span>
                        </div>
                        <div class="company-card-meta">${w.member_count || ''} a'zo • <span class="team-type-badge bot">bot</span></div>
                    </div>
                `;
            }).join('');
        }

        // Telegram guruhlar section
        if (groups.length) {
            html += `<div class="cmp-action-title" style="margin:16px 0 8px">${IC.comment} Telegram guruhlar</div>`;
            html += groups.map(g => {
                return `
                    <div class="company-card" onclick="openCompanyDetail(${g.id},'${escapeHtml(g.title || g.name)}',false)">
                        <div class="company-card-row">
                            <span class="company-card-name">${IC.team} ${escapeHtml(g.title || g.name)}</span>
                            <span class="team-type-badge group">guruh</span>
                        </div>
                        <div class="company-card-meta">${g.member_count || ''} a'zo</div>
                    </div>
                `;
            }).join('');
        }

        list.innerHTML = html;
    } catch (e) {
        list.innerHTML = '<div class="sp-loading">❌ Xatolik</div>';
    }
}

function closeCompaniesPanel() {
    const panel = document.getElementById('companies-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

let _currentCompanyIsAdmin = false;
let _editModeActive = false;

async function openCompanyDetail(companyId, companyName, isAdmin) {
    const panel = document.getElementById('company-detail-panel');
    const body = document.getElementById('company-detail-body');
    const title = document.getElementById('company-detail-name');
    const editBtn = document.getElementById('company-edit-btn');
    if (!panel) return;
    if (title) title.textContent = companyName;
    _currentCompanyIsAdmin = !!isAdmin;
    _editModeActive = false;
    // Show edit button only for admins/owners
    if (editBtn) {
        if (isAdmin) editBtn.classList.remove('hidden');
        else editBtn.classList.add('hidden');
    }
    body.innerHTML = '<div class="sp-loading">⏳ Yuklanmoqda...</div>';
    panel.classList.remove('hidden');
    setTimeout(() => panel.classList.add('open'), 10);
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    try {
        const data = await apiRequest(`/companies/${companyId}/info`);
        renderCompanyDetail(companyId, data);
    } catch (e) {
        body.innerHTML = '<div class="sp-loading">❌ ' + escapeHtml(e.message || 'Xatolik') + '</div>';
    }
}

function toggleCompanyEdit() {
    _editModeActive = !_editModeActive;
    // Re-render with current cached data
    const body = document.getElementById('company-detail-body');
    if (!body) return;
    const editBtn = document.getElementById('company-edit-btn');
    if (editBtn) editBtn.textContent = _editModeActive ? '✅' : '✏️';
    // Find all member rows and toggle edit controls
    body.querySelectorAll('.member-edit-actions').forEach(el => {
        el.style.display = _editModeActive ? 'flex' : 'none';
    });
}

function renderCompanyDetail(companyId, data) {
    const body = document.getElementById('company-detail-body');
    const isOwner = data.is_owner;
    const isAdmin = data.is_admin || isOwner;
    const members = data.members || [];

    let html = '';

    if (!isOwner) {
        // Regular member — show leave button
        html += `
            <div class="cmp-action-area">
                <div class="cmp-action-title">⚠️ Jamoadan chiqish</div>
                <button class="btn-danger" style="width:100%;padding:12px;" onclick="leaveCompanyFromPanel(${companyId})">
                    🚪 Jamoadan chiqish
                </button>
            </div>
        `;
    } else {
        // Owner — show edit options + delete
        html += `
            <div class="cmp-action-area">
                <div class="cmp-action-title">${IC.crown} Owner imkoniyatlari</div>
                <button class="btn-primary" style="width:100%;padding:12px;margin-bottom:8px;" onclick="openInviteLink(${companyId})">
                    🔗 Taklif havolasi
                </button>
                <button class="btn-danger" style="width:100%;padding:12px;" onclick="deleteCompanyFromPanel(${companyId},'${escapeHtml(data.name || '')}')">
                    🗑 Jamoani o'chirish
                </button>
            </div>
        `;
    }

    // Members list
    html += `<div class="cmp-action-title" style="margin-bottom:10px">👥 A'zolar (${members.length})</div>`;
    html += members.map(m => {
        const roleLabel = m.is_owner ? IC.crown+' Owner' : (m.role === 'admin' ? IC.shield+' Admin' : IC.user+' A\'zo');
        const canEdit = isAdmin && !m.is_self && !m.is_owner;
        const canRole = isAdmin && !m.is_self && !m.is_owner;
        const actionsHtml = canEdit ? `
            <div class="member-edit-actions" style="display:none">
                <button class="member-role-btn" onclick="openRoleSheet(${companyId},${m.id},'${escapeHtml(m.name)}','${m.role||'member'}')">
                    ${IC.crown} Rol
                </button>
                <button class="member-edit-btn" onclick="openReassignSheet(${companyId},${m.id},'${escapeHtml(m.name)}')">
                    🔄
                </button>
                <button class="member-remove-btn" onclick="kickMember(${companyId},${m.id},'${escapeHtml(m.name)}')">
                    Chiqar
                </button>
            </div>
        ` : '';
        const selfBadge = m.is_self ? ' <span style="color:var(--accent);font-size:11px">(siz)</span>' : '';
        return `
            <div class="member-edit-row">
                <div class="cmp-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</div>
                <div class="member-edit-info">
                    <div class="member-edit-name">${escapeHtml(m.name)}${selfBadge}</div>
                    <div class="member-edit-role">${roleLabel}${m.position ? ' · ' + escapeHtml(m.position) : ''}</div>
                </div>
                ${actionsHtml}
            </div>
        `;
    }).join('');

    body.innerHTML = html;
    // Sync edit mode state
    if (_editModeActive) {
        body.querySelectorAll('.member-edit-actions').forEach(el => {
            el.style.display = 'flex';
        });
    }
}

function closeCompanyDetail() {
    const panel = document.getElementById('company-detail-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

async function leaveCompanyFromPanel(companyId) {
    if (!confirm('Haqiqatan ham bu jamoadan chiqmoqchimisiz?')) return;
    try {
        await apiRequest(`/companies/${companyId}/leave`, 'DELETE');
        showToast('✅ Jamoadan chiqdingiz');
        closeCompanyDetail();
        closeCompaniesPanel();
        await changeWorkspace();
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

async function deleteCompanyFromPanel(companyId, companyName) {
    const name = companyName || 'bu jamoani';
    if (!confirm(`⚠️ "${name}" jamoasini O'CHIRIB YUBORISHNI tasdiqlaysizmi?\n\nBarcha vazifalar va ma'lumotlar butunlay yo'qoladi. Bu amal qaytarib bo'lmaydi!`)) return;
    try {
        await apiRequest(`/companies/${companyId}`, 'DELETE');
        showToast('✅ Jamoa o\'chirildi');
        closeCompanyDetail();
        closeCompaniesPanel();
        await changeWorkspace();
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

async function kickMember(companyId, userId, userName) {
    if (!confirm(`${userName} ni jamoadan chiqarishni tasdiqlaysizmi?`)) return;
    try {
        await apiRequest(`/companies/${companyId}/members/${userId}`, 'DELETE');
        showToast(`✅ ${userName} chiqarildi`);
        // Refresh company detail
        const data = await apiRequest(`/companies/${companyId}/info`);
        renderCompanyDetail(companyId, data);
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

// ===== Role Assignment =====
function openRoleSheet(companyId, userId, userName, currentRole) {
    const existing = document.getElementById('role-sheet-overlay');
    if (existing) existing.remove();

    const roles = [
        { value: 'admin',  icon: IC.shield, label: 'Admin',  desc: 'Jamoa boshqarish, a\'zo qo\'shish/chiqarish huquqi' },
        { value: 'member', icon: IC.user,   label: 'A\'zo', desc: 'Odatiy foydalanuvchi, faqat o\'z vazifalari' },
    ];

    const overlay = document.createElement('div');
    overlay.id = 'role-sheet-overlay';
    overlay.className = 'gp-overlay';
    overlay.innerHTML = `
        <div class="gp-sheet">
            <div class="gp-sheet-header">
                <span class="gp-sheet-title">${IC.crown} ${escapeHtml(userName)} — Rol tanlash</span>
                <button class="gp-close-btn" onclick="document.getElementById('role-sheet-overlay').remove()">✕</button>
            </div>
            <div class="gp-sheet-body" style="padding:16px">
                <p style="font-size:13px;color:var(--text3);margin-bottom:14px">
                    Yangi rol belgilang. O'zgarish darhol kuchga kiradi.
                </p>
                ${roles.map(r => `
                    <div class="role-option ${r.value === currentRole ? 'role-selected' : ''}"
                         onclick="assignRole(${companyId}, ${userId}, '${r.value}')">
                        <span class="role-option-icon">${r.icon}</span>
                        <div class="role-option-info">
                            <div class="role-option-label">${r.label}</div>
                            <div class="role-option-desc">${r.desc}</div>
                        </div>
                        ${r.value === currentRole ? '<span class="role-current">✓ Joriy</span>' : ''}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

async function assignRole(companyId, userId, newRole) {
    document.getElementById('role-sheet-overlay')?.remove();
    try {
        await apiRequest(`/companies/${companyId}/members/${userId}`, 'PUT', { role: newRole });
        const roleLabel = newRole === 'admin' ? 'Admin' : 'A\'zo';
        showToast(`✅ Rol o'zgartirildi: ${roleLabel}`);
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        // Refresh company detail
        const data = await apiRequest(`/companies/${companyId}/info`);
        renderCompanyDetail(companyId, data);
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

async function openInviteLink(companyId) {
    try {
        const data = await apiRequest('/invite-link');
        const link = data.link;
        if (navigator.share) {
            await navigator.share({ text: link });
        } else if (navigator.clipboard) {
            await navigator.clipboard.writeText(link);
            showToast('✅ Havola nusxalandi!');
        } else {
            showToast(link);
        }
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

// Task reassignment sheet
let _reassignFromId = null;
let _reassignCompanyId = null;
let _reassignFromName = '';

async function openReassignSheet(companyId, fromUserId, fromUserName) {
    _reassignFromId = fromUserId;
    _reassignCompanyId = companyId;
    _reassignFromName = fromUserName;

    const existing = document.getElementById('reassign-sheet-overlay');
    if (existing) existing.remove();

    // Get members for selector
    let memberOptions = '';
    try {
        const data = await apiRequest(`/companies/${companyId}/info`);
        memberOptions = (data.members || [])
            .filter(m => m.id !== fromUserId && !m.is_owner)
            .map(m => `<div class="gp-member-row" onclick="_doReassign(${m.id},'${escapeHtml(m.name)}')">
                <span class="gp-member-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</span>
                <span class="gp-member-name">${escapeHtml(m.name)}</span>
            </div>`).join('');
    } catch (e) {}

    if (!memberOptions) {
        showToast('Boshqa a\'zolar yo\'q', true);
        return;
    }

    const overlay = document.createElement('div');
    overlay.id = 'reassign-sheet-overlay';
    overlay.className = 'reassign-sheet-overlay';
    overlay.innerHTML = `
        <div class="reassign-sheet">
            <div class="reassign-title">🔄 ${escapeHtml(fromUserName)} vazifalarini topshirish</div>
            <p style="font-size:13px;color:var(--text3);margin-bottom:14px">
                ${escapeHtml(fromUserName)}ning barcha faol vazifalari yangi ijrochiga o'tkaziladi.
            </p>
            ${memberOptions}
            <button onclick="document.getElementById('reassign-sheet-overlay').remove()"
                style="width:100%;margin-top:12px;padding:12px;background:var(--bg3);border:none;border-radius:12px;color:var(--text2);font-weight:700;cursor:pointer">
                Bekor qilish
            </button>
        </div>
    `;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

async function _doReassign(toUserId, toUserName) {
    document.getElementById('reassign-sheet-overlay')?.remove();
    if (!_reassignCompanyId || !_reassignFromId) return;
    try {
        const r = await apiRequest(`/companies/${_reassignCompanyId}/reassign`, 'POST', {
            from_user_id: _reassignFromId,
            to_user_id: toUserId,
        });
        showToast(`✅ ${r.reassigned} ta vazifa ${toUserName}ga o'tkazildi`);
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        // Reload tasks
        await changeWorkspace();
    } catch (e) {
        showToast('❌ ' + (e.message || 'Xatolik'), true);
    }
}

// ================================================================
// SETTINGS PANEL
// ================================================================

function openSettingsPanel() {
    closeSidebar();
    const panel = document.getElementById('settings-panel');
    if (!panel) return;
    panel.classList.remove('hidden');
    setTimeout(() => panel.classList.add('open'), 10);

    // Highlight current language
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lang === I18N.lang);
    });

    // FX toggle holatini ko'rsatish
    document.getElementById('fx-sound-switch')?.classList.toggle('on', FX.isSoundOn());
    document.getElementById('fx-haptic-switch')?.classList.toggle('on', FX.isHapticOn());

    FX.tap();
}

function toggleFxSound() {
    const newVal = !FX.isSoundOn();
    FX.setSoundOn(newVal);
    document.getElementById('fx-sound-switch')?.classList.toggle('on', newVal);
    if (newVal) FX.success();
    else FX.tap();   // toggle off — bir marta hapt'ic kech
    showToast(newVal ? '🔊 Ovoz yoqildi' : '🔇 Ovoz o\'chirildi');
}

function toggleFxHaptic() {
    const newVal = !FX.isHapticOn();
    FX.setHapticOn(newVal);
    document.getElementById('fx-haptic-switch')?.classList.toggle('on', newVal);
    if (newVal) FX.success();
    showToast(newVal ? '📳 Tebranish yoqildi' : '🔕 Tebranish o\'chirildi');
}

function closeSettingsPanel() {
    const panel = document.getElementById('settings-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

// ═══════════════════════════════════════════════════════════════
//  AI YORDAMCHI (maslahatchi) moduli
// ═══════════════════════════════════════════════════════════════
let _aiEnabled = false;
let _aiHistory = [];        // [{role, content}]
let _aiBusy = false;

async function checkAiStatus() {
    try {
        const r = await apiRequest('/ai/status');
        _aiEnabled = !!r.ai_enabled;
    } catch (e) { _aiEnabled = false; }
    const item = document.getElementById('sb-ai-item');
    if (item) item.style.display = _aiEnabled ? '' : 'none';
    const hdrBtn = document.getElementById('app-ai-btn');
    if (hdrBtn) hdrBtn.style.display = _aiEnabled ? 'inline-flex' : 'none';
}

function openAiPanel() {
    if (!_aiEnabled) {
        showToast && showToast('🔒 AI yordamchi siz uchun yoqilmagan');
        return;
    }
    const panel = document.getElementById('ai-panel');
    if (!panel) return;
    panel.classList.remove('hidden');
    setTimeout(() => panel.classList.add('open'), 10);
    if (tg) tg.HapticFeedback?.impactOccurred('light');
    if (!_aiHistory.length) _aiRenderWelcome();
    setTimeout(() => document.getElementById('ai-chat-input')?.focus(), 320);
}

function closeAiPanel() {
    const panel = document.getElementById('ai-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

function clearAiChat() {
    _aiHistory = [];
    _aiRenderWelcome();
}

function _aiRenderWelcome() {
    const body = document.getElementById('ai-chat-body');
    if (!body) return;
    const name = (window._currentUserName || '').split(' ')[0] || '';
    body.innerHTML = `
        <div class="ai-welcome">
            <div class="ai-welcome-emoji">🤖</div>
            <div class="ai-welcome-title">Salom${name ? ', ' + escapeHtml(name) : ''}! 👋</div>
            <div class="ai-welcome-sub">Men sizning AI yordamchingizman. Vazifalaringizdan xabardorman va sizga yo'l-yo'riq ko'rsataman.</div>
            <div class="ai-suggest-row">
                <button class="ai-suggest" onclick="aiQuick('Bugun nimadan boshlasam yaxshi bo\\'ladi?')">📌 Nimadan boshlay?</button>
                <button class="ai-suggest" onclick="aiQuick('Qaysi vazifalarim shoshilinch?')">🔥 Shoshilinch ishlar</button>
                <button class="ai-suggest" onclick="aiQuick('Eng muhim vazifani ertaga soat 10:00 da eslat')">⏰ Eslatma qo'y</button>
                <button class="ai-suggest" onclick="aiQuick('Ishlarni qanday tartibda qilsam unumli bo\\'ladi?')">🎯 Reja tuzib ber</button>
            </div>
        </div>`;
}

function aiAutoGrow(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function aiInputKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        aiSendMessage();
    }
}

function aiQuick(text) {
    const inp = document.getElementById('ai-chat-input');
    if (inp) inp.value = text;
    aiSendMessage();
}

function _aiAppendMsg(role, html) {
    const body = document.getElementById('ai-chat-body');
    if (!body) return null;
    // welcome bloki bo'lsa olib tashlaymiz
    const wel = body.querySelector('.ai-welcome');
    if (wel) wel.remove();
    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-' + role;
    div.innerHTML = `<div class="ai-bubble">${html}</div>`;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return div;
}

async function aiSendMessage() {
    if (_aiBusy) return;
    const inp = document.getElementById('ai-chat-input');
    const text = (inp?.value || '').trim();
    if (!text) return;
    inp.value = '';
    aiAutoGrow(inp);

    _aiAppendMsg('user', escapeHtml(text));
    _aiHistory.push({ role: 'user', content: text });
    if (typeof FX !== 'undefined') FX.play && FX.play('send');

    _aiBusy = true;
    const btn = document.getElementById('ai-send-btn');
    if (btn) btn.disabled = true;
    const typing = _aiAppendMsg('assistant', '<span class="ai-typing"><i></i><i></i><i></i></span>');

    try {
        const r = await apiRequest('/ai/chat', 'POST', {
            message: text,
            company_id: currentWorkspaceId || 'personal',
            history: _aiHistory.slice(-8),
        });
        const reply = (r.text || 'Tushunmadim, qaytadan yozing.');
        if (typing) typing.remove();
        _aiAppendMsg('assistant', _aiFormat(reply));
        _aiHistory.push({ role: 'assistant', content: reply });
        if (r.reminder_set && typeof FX !== 'undefined') FX.play && FX.play('success');
    } catch (e) {
        if (typing) typing.remove();
        _aiAppendMsg('assistant', '❌ Xatolik: ' + escapeHtml(e.message || 'qaytadan urining'));
    } finally {
        _aiBusy = false;
        if (btn) btn.disabled = false;
    }
}

// Oddiy formatlash: <b>, qatorlar; xavfsiz (server HTMLni ishonchli yuboradi)
function _aiFormat(s) {
    return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/&lt;b&gt;/g, '<b>').replace(/&lt;\/b&gt;/g, '</b>')
        .replace(/&lt;code&gt;/g, '<code>').replace(/&lt;\/code&gt;/g, '</code>')
        .replace(/\n/g, '<br>');
}

// ═══════════════════════════════════════════════════════════════
//  MUROJAAT (Taklif va shikoyat) moduli
// ═══════════════════════════════════════════════════════════════

let _fbAnon = 0;
let _fbType = 'suggestion';
let _fbMedia = [];
let _fbIsAdmin = false;
let _fbInboxFilter = 'pending';

function fbEsc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function openFeedbackPanel() {
    closeSidebar();
    const panel = document.getElementById('feedback-panel');
    if (!panel) return;
    panel.classList.remove('hidden');
    setTimeout(() => panel.classList.add('open'), 10);
    if (tg) tg.HapticFeedback?.impactOccurred('light');

    // Admin tekshiruvi → "Kelganlar" tabini ko'rsatamiz
    try {
        const meta = await apiRequest('/feedback/meta');
        _fbIsAdmin = !!meta.is_admin;
    } catch (e) { _fbIsAdmin = false; }
    document.getElementById('fb-tab-inbox')?.classList.toggle('hidden', !_fbIsAdmin);

    fbSwitch('new');
}

function closeFeedbackPanel() {
    const panel = document.getElementById('feedback-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

function fbSwitch(view) {
    ['new', 'my', 'inbox'].forEach(v => {
        document.getElementById('fb-view-' + v)?.classList.toggle('hidden', v !== view);
        document.getElementById('fb-tab-' + v)?.classList.toggle('active', v === view);
    });
    if (view === 'my') fbLoadMy();
    if (view === 'inbox') fbLoadInbox();
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function fbSetAnon(v) {
    _fbAnon = v ? 1 : 0;
    document.querySelectorAll('#fb-anon-seg .fb-seg-btn').forEach(b =>
        b.classList.toggle('active', String(b.dataset.val) === String(_fbAnon)));
    const hint = document.getElementById('fb-anon-hint');
    if (hint) hint.textContent = _fbAnon
        ? "🕵️ Hech kim sizning kimligingizni bilmaydi."
        : "👤 Adminlar sizning kimligingizni ko'radi.";
}

function fbSetType(v) {
    _fbType = v;
    document.querySelectorAll('#fb-type-seg .fb-seg-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.val === v));
}

async function fbUploadFiles(files) {
    if (!files || !files.length) return;
    for (const file of files) {
        if (_fbMedia.length >= 10) { tg?.showAlert?.('Maksimum 10 ta mediya'); break; }
        try {
            const fd = new FormData();
            fd.append('file', file);
            const headers = {};
            applyAuthHeaders(headers);
            const res = await fetch(API_BASE + '/feedback/upload', { method: 'POST', headers, body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Yuklash xatosi');
            _fbMedia.push(data);
        } catch (e) {
            tg?.showAlert?.('❌ ' + (e.message || e));
        }
    }
    document.getElementById('fb-file-input').value = '';
    fbRenderMedia();
}

function fbRenderMedia() {
    const wrap = document.getElementById('fb-media-list');
    if (!wrap) return;
    if (!_fbMedia.length) { wrap.innerHTML = ''; return; }
    wrap.innerHTML = _fbMedia.map((m, i) => {
        const isImg = m.file_type === 'photo';
        const inner = isImg
            ? `<img src="${m.file_url}" alt="">`
            : `<span class="fb-media-doc">📎</span>`;
        return `<div class="fb-media-item">${inner}<button class="fb-media-x" onclick="fbRemoveMedia(${i})">×</button></div>`;
    }).join('');
}

function fbRemoveMedia(i) {
    _fbMedia.splice(i, 1);
    fbRenderMedia();
}

async function fbSubmit() {
    const content = (document.getElementById('fb-content')?.value || '').trim();
    if (content.length < 3) { tg?.showAlert?.('Iltimos, murojaat matnini yozing.'); return; }
    const btn = document.getElementById('fb-submit');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Yuborilmoqda...'; }
    try {
        await apiRequest('/feedback', 'POST', {
            type: _fbType,
            is_anonymous: !!_fbAnon,
            content,
            attachments: _fbMedia,
        });
        tg?.HapticFeedback?.notificationOccurred('success');
        // Reset
        document.getElementById('fb-content').value = '';
        _fbMedia = []; fbRenderMedia();
        tg?.showAlert?.(_fbAnon
            ? '✅ Murojaatingiz anonim yuborildi! Javob shu yerda ko\'rinadi.'
            : '✅ Murojaatingiz yuborildi! Javob shu yerda ko\'rinadi.');
        fbSwitch('my');
    } catch (e) {
        tg?.showAlert?.('❌ ' + (e.message || e));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📨 Yuborish'; }
    }
}

function _fbStatusBadge(status, label) {
    const cls = status === 'resolved' ? 'fb-st-resolved' : 'fb-st-pending';
    return `<span class="fb-status ${cls}">${fbEsc(label)}</span>`;
}

function _fbTypeChip(item) {
    const em = item.type === 'complaint' ? '😠' : '💡';
    return `<span class="fb-type-chip">${em} ${fbEsc(item.type_label)}</span>`;
}

function _fbAttachHtml(atts) {
    if (!atts || !atts.length) return '';
    const parts = atts.map(a => {
        if (!a.file_url) return `<span class="fb-att-file">📎 ${fbEsc(a.file_name || 'media')}</span>`;
        if (a.file_type === 'photo')
            return `<a href="${a.file_url}" target="_blank" class="fb-att-thumb"><img src="${a.file_url}" alt=""></a>`;
        if (a.file_type === 'video')
            return `<video class="fb-att-video" src="${a.file_url}" controls preload="metadata"></video>`;
        if (a.file_type === 'voice' || a.file_type === 'audio')
            return `<audio class="fb-att-audio" src="${a.file_url}" controls preload="none"></audio>`;
        return `<a href="${a.file_url}" target="_blank" class="fb-att-file">📎 ${fbEsc(a.file_name || 'fayl')}</a>`;
    });
    return `<div class="fb-att-row">${parts.join('')}</div>`;
}

function _fbRepliesHtml(replies) {
    if (!replies || !replies.length) return '';
    return replies.map(r =>
        `<div class="fb-reply"><div class="fb-reply-head">✍️ ${fbEsc(r.admin_name)} · ${fbEsc(r.created_at)}</div><div class="fb-reply-body">${fbEsc(r.content)}</div></div>`
    ).join('');
}

async function fbLoadMy() {
    const wrap = document.getElementById('fb-my-list');
    if (!wrap) return;
    wrap.innerHTML = '<div class="sp-loading">⏳ Yuklanmoqda...</div>';
    try {
        const data = await apiRequest('/feedback/my');
        const items = data.items || [];
        if (!items.length) {
            wrap.innerHTML = '<div class="fb-empty">📭 Hali murojaatingiz yo\'q.<br>«Yangi» bo\'limidan yuboring.</div>';
            return;
        }
        wrap.innerHTML = items.map(it => `
            <div class="fb-card">
                <div class="fb-card-top">
                    ${_fbTypeChip(it)}
                    ${it.is_anonymous ? '<span class="fb-anon-chip">🕵️ Anonim</span>' : ''}
                    ${_fbStatusBadge(it.status, it.status_label)}
                </div>
                <div class="fb-card-content">${fbEsc(it.content)}</div>
                ${_fbAttachHtml(it.attachments)}
                <div class="fb-card-date">🕐 ${fbEsc(it.created_at)} · #${it.id}</div>
                ${_fbRepliesHtml(it.replies)}
            </div>
        `).join('');
    } catch (e) {
        wrap.innerHTML = `<div class="fb-empty">❌ ${fbEsc(e.message || e)}</div>`;
    }
}

function fbInboxFilter(f) {
    _fbInboxFilter = f;
    document.querySelectorAll('.fb-filter-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.f === f));
    fbLoadInbox();
}

async function fbLoadInbox() {
    const wrap = document.getElementById('fb-inbox-list');
    if (!wrap) return;
    wrap.innerHTML = '<div class="sp-loading">⏳ Yuklanmoqda...</div>';
    try {
        const q = _fbInboxFilter ? ('?status=' + _fbInboxFilter) : '';
        const data = await apiRequest('/feedback/inbox' + q);
        const items = data.items || [];
        if (!items.length) {
            wrap.innerHTML = '<div class="fb-empty">📭 Murojaat yo\'q.</div>';
            return;
        }
        wrap.innerHTML = items.map(it => {
            const canReply = it.status !== 'resolved';
            return `
            <div class="fb-card">
                <div class="fb-card-top">
                    ${_fbTypeChip(it)}
                    ${it.is_anonymous ? '<span class="fb-anon-chip">🕵️ Anonim</span>' : ''}
                    ${_fbStatusBadge(it.status, it.status_label)}
                </div>
                <div class="fb-from">${fbEsc(it.from_name || '')}</div>
                <div class="fb-card-content">${fbEsc(it.content)}</div>
                ${_fbAttachHtml(it.attachments)}
                <div class="fb-card-date">🕐 ${fbEsc(it.created_at)} · #${it.id}</div>
                ${_fbRepliesHtml(it.replies)}
                ${canReply ? `
                <div class="fb-reply-box">
                    <textarea class="fb-reply-input" id="fb-reply-${it.id}" rows="2" placeholder="Javob yozing..."></textarea>
                    <div class="fb-reply-actions">
                        <button class="fb-reply-send" onclick="fbSendReply(${it.id})">📨 Javob</button>
                        <button class="fb-resolve-btn" onclick="fbResolve(${it.id})">✅ Yechildi</button>
                    </div>
                </div>` : ''}
            </div>`;
        }).join('');
    } catch (e) {
        wrap.innerHTML = `<div class="fb-empty">❌ ${fbEsc(e.message || e)}</div>`;
    }
}

async function fbSendReply(id) {
    const ta = document.getElementById('fb-reply-' + id);
    const content = (ta?.value || '').trim();
    if (content.length < 2) { tg?.showAlert?.('Javob matnini yozing.'); return; }
    try {
        await apiRequest(`/feedback/${id}/reply`, 'POST', { content });
        tg?.HapticFeedback?.notificationOccurred('success');
        tg?.showAlert?.('✅ Javob yuborildi.');
        fbLoadInbox();
    } catch (e) {
        tg?.showAlert?.('❌ ' + (e.message || e));
    }
}

async function fbResolve(id) {
    try {
        await apiRequest(`/feedback/${id}/resolve`, 'POST', {});
        tg?.HapticFeedback?.notificationOccurred('success');
        fbLoadInbox();
    } catch (e) {
        tg?.showAlert?.('❌ ' + (e.message || e));
    }
}

