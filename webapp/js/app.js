/**
 * TaskBot Mini App - Frontend Logic
 */

const tg = window.Telegram?.WebApp;
const API_BASE = '/api';

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
        applyI18n();
        if (typeof showToast === 'function') showToast(tr('common.success'));
    } catch (e) {
        console.warn('set lang failed:', e);
    }
}
let currentFilter = 'active';
let allTasks = [];
let currentTaskId = null;
// Sub-task mode state
let _subtaskParentId    = null;
let _subtaskParentTitle = null;
let currentWorkspaceId = 'personal';
let currentWorkspaceName = 'Shaxsiy';
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

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    if (tg) {
        tg.ready();
        tg.expand();
        tg.enableClosingConfirmation();
        
        // Force dark theme — override any Telegram light theme vars
        document.body.style.setProperty('--tg-theme-bg-color',          '#0A0A14');
        document.body.style.setProperty('--tg-theme-secondary-bg-color','#11111E');
        document.body.style.setProperty('--tg-theme-text-color',         '#EEEEF8');
        document.body.style.setProperty('--tg-theme-hint-color',         '#9090B0');
        document.body.style.setProperty('--tg-theme-link-color',         '#6366F1');
        document.body.style.setProperty('--tg-theme-button-color',       '#6366F1');
        document.body.style.setProperty('--tg-theme-button-text-color',  '#FFFFFF');
        try { tg.setHeaderColor('#0A0A14'); } catch(e) {}
        try { tg.setBackgroundColor('#0A0A14'); } catch(e) {}
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

// ===== Workspace Switcher =====
async function changeWorkspace() {
    const wsSelect = document.getElementById('workspace-select');
    if (!wsSelect) return;

    currentWorkspaceId = wsSelect.value;
    const opt = wsSelect.options[wsSelect.selectedIndex];
    currentWorkspaceName = opt ? opt.text : 'Shaxsiy';

    if (tg) tg.HapticFeedback?.selectionChanged();

    // Show/hide leave button
    const leaveBtn = document.getElementById('leave-workspace-btn');
    if (leaveBtn) {
        const isCompany = currentWorkspaceId !== 'personal' && currentWorkspaceId !== 'all';
        leaveBtn.classList.toggle('hidden', !isCompany);
        leaveBtn.onclick = () => leaveWorkspace(currentWorkspaceId);
    }

    updateCreateWorkspaceUI();

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
    externalAssignees = [];
    selectedResponsibleIds = [];
    companyMembers = [];

    if (currentWorkspaceId === 'personal' || currentWorkspaceId === 'all') {
        group.classList.add('hidden');
        if (list) list.innerHTML = '';
        renderResponsibleSection();
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
        const roleBadge = m.role === 'owner' ? '👑' : (m.role === 'admin' ? '🛡' : '👤');
        return `
            <div class="assignee-chip ${selected ? 'selected' : ''}" onclick="toggleAssignee(${m.id})">
                <span class="assignee-avatar">${escapeHtml(initial)}</span>
                <span class="assignee-name">${roleBadge} ${escapeHtml(m.name)}${m.is_self ? ' (siz)' : ''}</span>
                <span class="assignee-check">${selected ? '✓' : ''}</span>
            </div>`;
    }).join('');

    // Tashqi guruhdan qo'shilganlar
    const extHtml = externalAssignees.length ? `
        <div class="assignee-ext-header">➕ Boshqa guruhdan qo'shilganlar</div>
        ${externalAssignees.map(m => `
            <div class="assignee-chip selected ext-member">
                <span class="assignee-avatar">${escapeHtml((m.name||'?')[0].toUpperCase())}</span>
                <span class="assignee-name">👤 ${escapeHtml(m.name)} <span class="ext-group-tag">${escapeHtml(m.group_name)}</span></span>
                <span class="assignee-check remove-ext" onclick="event.stopPropagation();removeExternalAssignee(${m.id})">✕</span>
            </div>`).join('')}
    ` : '';

    // "Boshqa guruhdan qo'shish" tugmasi
    const addBtn = `
        <button class="assignee-add-group-btn" onclick="openGroupPickerSheet()">
            ➕ Boshqa guruhdan qo'shish
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
        + `<button class="resp-pick-btn" onclick="openResponsibleSheet()">➕ Mas'ul qo'shish</button>`;
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
                <span class="gp-group-icon">🏢</span>
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
    if (title) title.textContent = '🏢 ' + groupName;
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
    const mn = ['Yanvar','Fevral','Mart','Aprel','May','Iyun','Iyul','Avgust','Sentyabr','Oktyabr','Noyabr','Dekabr'];
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
    if (statsEl) statsEl.textContent = `${stats.total || 0} vazifa - ${stats.completion_rate || 0}% bajarildi`;
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
            titleEl.textContent = `📊 ${stats.member_name}`;
        } else {
            titleEl.textContent = '📊 Statistikangiz';
        }
    }

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
}

const _ROLE_META = {
    owner:  { icon: '👑', label: 'Owner',  cls: 'smf-role-owner'  },
    admin:  { icon: '⭐', label: 'Admin',  cls: 'smf-role-admin'  },
    member: { icon: '👤', label: 'Member', cls: 'smf-role-member' },
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
        const roleMark = e.role === 'owner' ? ' 👑' : e.role === 'admin' ? ' ⭐' : '';
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
                    label: '🔴 Boshlanmagan',
                    data: newTasks,
                    backgroundColor: 'rgba(239,68,68,0.82)',
                    borderColor: '#EF4444',
                    borderWidth: 1.5,
                    borderRadius: { topLeft: 0, topRight: 0, bottomLeft: 6, bottomRight: 6 },
                    borderSkipped: 'bottom',
                    stack: 'tasks',
                },
                {
                    label: '🟡 Jarayonda',
                    data: inProgress,
                    backgroundColor: 'rgba(234,179,8,0.85)',
                    borderColor: '#EAB308',
                    borderWidth: 1.5,
                    borderRadius: 0,
                    borderSkipped: false,
                    stack: 'tasks',
                },
                {
                    label: '🟢 Bajarildi',
                    data: done,
                    backgroundColor: 'rgba(34,197,94,0.85)',
                    borderColor: '#22C55E',
                    borderWidth: 1.5,
                    borderRadius: 0,
                    borderSkipped: false,
                    stack: 'tasks',
                },
                {
                    label: '🟠 Kechikdi',
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
                            const roleTxt = emp.role === 'owner' ? '👑 Owner' :
                                            emp.role === 'admin' ? '⭐ Admin' : '👤 Member';
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
            : (isDone ? '' : '<div class="wf-cur-step" style="color:var(--text3)">Kutilmoqda...</div>');

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
            <div class="wf-card-footer">📅 ${w.created_at} &nbsp;•&nbsp; 🪜 ${w.total_steps} qadam</div>
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
                <span>🪜 Qadamlar: ${w.done_steps}/${w.total_steps}</span>
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
                <div class="modal-detail-label">📍 Holat</div>
                <div class="modal-detail-value">${statusTxt}</div>
            </div>
            <div class="modal-detail">
                <div class="modal-detail-label">📅 Yaratildi</div>
                <div class="modal-detail-value">${w.created_at}</div>
            </div>
        </div>
        ${w.description ? `<div class="modal-detail"><div class="modal-detail-label">Tavsif</div><div class="modal-detail-value">${escapeHtml(w.description)}</div></div>` : ''}
        ${progressBar}
        <div class="modal-detail-label" style="margin-bottom:8px">🪜 QADAMLAR</div>
    `;

    // ---- Steps ----
    w.steps.forEach(s => {
        const icon = s.status === 'done' ? IC.done : s.status === 'active' ? IC.play : s.status === 'blocked' ? IC.pause : IC.circle;
        const isCur = s.status === 'active';
        const cardStyle = isCur
            ? 'background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.35);border-radius:14px;padding:12px 14px;margin-bottom:10px'
            : 'background:var(--glass);border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-bottom:10px;opacity:' + (s.status==='done'?'0.75':'1');

        let meta = [];
        if (s.started_at)   meta.push(`▶ ${s.started_at}`);
        if (s.completed_at) meta.push(`✅ ${s.completed_at}`);
        if (s.deadline)     meta.push(`⏰ ${s.deadline}`);
        const metaHtml = meta.length ? `<div style="font-size:11px;color:var(--text3);margin-top:5px;display:flex;gap:10px;flex-wrap:wrap">${meta.map(m=>`<span>${m}</span>`).join('')}</div>` : '';

        let noteHtml = '';
        if (s.comments && s.comments.length) {
            noteHtml = s.comments.map(c =>
                `<div style="font-size:12px;background:var(--glass2);padding:6px 10px;border-radius:8px;margin-top:5px;color:var(--text2)">
                    <b style="color:var(--text)">${escapeHtml(c.user)}</b> <span style="float:right;font-size:10px;color:var(--text3)">${c.created_at}</span><br>${escapeHtml(c.content)}
                </div>`
            ).join('');
        } else if (s.note) {
            noteHtml = `<div style="font-size:12px;background:var(--glass2);padding:6px 10px;border-radius:8px;margin-top:5px;color:var(--text2)">💬 ${escapeHtml(s.note)}</div>`;
        }

        let attsHtml = '';
        if (s.attachments && s.attachments.length) {
            attsHtml = `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${s.attachments.map(a=>`<span style="font-size:11px;background:var(--glass2);padding:3px 8px;border-radius:8px;color:var(--text2)">${typeEm[a.file_type]||'📎'} ${escapeHtml(a.file_name||a.file_type)}</span>`).join('')}</div>`;
        }

        const meBtnHtml = s.is_me && (s.status === 'active' || s.status === 'pending') && !isDone
            ? `<button class="modal-action-btn btn-primary" style="margin-top:8px" onclick="handleStepAction(${w.task_id},'${s.status}');closeWfDetailModal()">
                ${s.status==='pending'?'▶️ Boshlash':'✅ Tugatish'}
               </button>` : '';

        bodyHtml += `
            <div style="${cardStyle}">
                <div style="display:flex;gap:10px;align-items:flex-start">
                    <div style="font-size:20px;line-height:1;margin-top:1px">${icon}</div>
                    <div style="flex:1;min-width:0">
                        <div style="font-size:14px;font-weight:700;color:var(--text)">${s.order}. ${escapeHtml(s.title)}</div>
                        <div style="font-size:12px;color:var(--text2);margin-top:2px">
                            👤 ${escapeHtml(s.assignee_name)}${s.is_me ? ' <b style="color:var(--accent)">(siz)</b>' : ''}
                        </div>
                        ${metaHtml}${noteHtml}${attsHtml}${meBtnHtml}
                    </div>
                </div>
            </div>`;
    });

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
// SVG icon helpers
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
};

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
        const FB = { low:'🟢 Past', medium:'🟡 O\'rta', high:'🟠 Muhum', urgent:'🔴 Juda muhum' };
        return FB[priority] || priority;
    }
    return translated;
}

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

    // Root tasks only
    let filtered = allTasks.filter(t => !t.parent_id);
    if (currentFilter === 'active') {
        filtered = filtered.filter(t => !['done', 'cancelled'].includes(t.status));
    } else if (currentFilter === 'done') {
        filtered = filtered.filter(t => t.status === 'done');
    } else if (currentFilter === 'overdue') {
        filtered = filtered.filter(t => t.status === 'overdue');
    }

    // Also include sub-tasks the current user is assigned to
    const myId = window._myUserId;
    if (myId) {
        const mySubtasks = allTasks.filter(t =>
            t.parent_id &&
            t.assignees && t.assignees.some(a => a.id === myId) &&
            !filtered.some(f => (subtaskMap[f.id] || []).some(c => c.id === t.id))
        );
        // Apply same status filter
        const filteredSubs = currentFilter === 'active'
            ? mySubtasks.filter(t => !['done','cancelled'].includes(t.status))
            : currentFilter === 'done' ? mySubtasks.filter(t => t.status === 'done')
            : currentFilter === 'overdue' ? mySubtasks.filter(t => t.status === 'overdue')
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

    // Deadline row — live countdown
    let dlHtml = '';
    if (task.deadline) {
        const icon = dlUrgent ? IC.fire : IC.clock;
        const dlCls = dlUrgent ? 'tc-dl-urgent' : (dlSoon ? 'tc-dl-soon' : 'tc-dl-normal');
        dlHtml = `<div class="tc-row ${dlCls} tc-countdown" data-deadline="${task.deadline}" data-status="${task.status}">${icon} <span class="tc-countdown-txt">${formatCountdown(task.deadline, task.status)}</span></div>`;
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
        
        // Use i18n-resolved labels
        const priorityNames = new Proxy({}, { get: (_, p) => getPriorityLabel(p) });
        const statusNames   = new Proxy({}, { get: (_, s) => getStatusLabel(s) });

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
            new: 'Yangi', in_progress: 'Jarayonda', review: 'Ko\'rilmoqda',
            done: 'Bajarildi', overdue: 'Kechikdi', cancelled: 'Bekor',
        };

        // Masul (responsible)
        if (task.responsible_name) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">⭐ Masul (Responsible)</div>
                    <div class="modal-detail-value"><span class="resp-badge">⭐ ${escapeHtml(task.responsible_name)}</span></div>
                </div>
            `;
        }

        if (task.assignees && task.assignees.length > 0) {
            // Mas'ullar va kuzatuvchilarni ajratib ko'rsatamiz
            const responsible = task.assignees.filter(a => a.is_responsible);
            const observers   = task.assignees.filter(a => !a.is_responsible);

            const makeRow = (a, isResp) => {
                const st = a.status || 'new';
                const roleIcon = isResp ? '⭐' : '👁';
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
                        <span class="subtask-status">${isDone ? '✅' : '⬜'}</span>
                        <span class="subtask-title">${escapeHtml(s.title.slice(0, 50))}</span>
                    </div>
                `;
            }).join('');
            const addBtn = (!hasParent)
                ? `<button class="subtask-add-btn" onclick="openSubtaskTypePicker(${task.id})">➕ Sub-task qo'shish</button>`
                : '';
            bodyHtml += `
                <div class="subtask-section">
                    <div class="subtask-section-title">📂 Sub-tasklar${subtasks.length ? ' ('+subtasks.length+')' : ''}</div>
                    ${subItems || '<div style="font-size:12px;color:var(--text2);margin-bottom:6px">Hali sub-task yo\'q</div>'}
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
                            <span class="comment-author">👤 ${authorName}</span>
                            <span class="comment-time">${commentTime}</span>
                        </div>
                        ${commentText ? `<div class="comment-text">${commentText}</div>` : ''}
                    </div>
                `;
            }).join('');
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">💬 Izohlar (${comments.length})</div>
                    <div class="task-comments-list">${commentsHtml}</div>
                </div>
            `;
        }

        // Media button — media gallery ochish
        const atts = task.attachments || [];
        {
            const mediaCount = atts.length;
            const mediaLabel = tr('app.media.title') || '📎 Mediya';
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

        // Tarix — barcha harakatlar ko'rsatiladi
        if (task.history && task.history.length > 0) {
            bodyHtml += `
                <div class="modal-detail">
                    <div class="modal-detail-label">🕐 So'nggi harakatlari (${task.history.length})</div>
                    <div class="timeline" id="task-timeline-${task.id}">${_renderTimeline(task.history)}</div>
                </div>
            `;
        }

        document.getElementById('modal-body').innerHTML = bodyHtml;

        // Actions
        let actionsHtml = '';
        const myStatus       = task.my_status;
        const isWorkflow     = task.has_workflow === true;
        const isResponsible  = task.my_is_responsible === true;
        const isObserver     = myStatus && !isResponsible;

        // Status + action buttons block
        const statusColors = { new:'#818CF8', in_progress:'#FBBF24', done:'#34D399', cancelled:'#6B7280', review:'#22D3EE' };
        const statusIcons  = { new:'🆕', in_progress:'⚙️', done:'✅', cancelled:'🚫', review:'🔍' };

        if (myStatus) {
            const sColor = statusColors[myStatus] || '#818CF8';
            const sIcon  = statusIcons[myStatus] || '📌';
            const sLabel = statusShort[myStatus] || myStatus;
            const roleLabel = isResponsible ? IC.star+' Mas\'ul' : IC.eye+' Kuzatuvchi';
            actionsHtml += `
                <div class="task-status-card" style="--s-color:${sColor}">
                    <div class="tsc-role">${roleLabel}</div>
                    <div class="tsc-status">${sIcon} ${sLabel}</div>
                </div>`;
        }

        if (isObserver) {
            actionsHtml += `<div class="observer-badge">👁 Status faqat mas'ul shaxs tomonidan o'zgartiriladi</div>`;
        }

        if (myStatus && isResponsible && !isWorkflow) {
            let btnClass = 'wf-btn-start', btnText = IC.play+' Boshlashni boshlash';
            if (myStatus === 'new')         { btnClass = 'wf-btn-start'; btnText = IC.play+' Boshlash'; }
            if (myStatus === 'in_progress') { btnClass = 'wf-btn-done';  btnText = IC.check+' Bajarildi deb belgilash'; }
            if (myStatus === 'done')        { btnClass = 'wf-btn-secondary'; btnText = IC.check+' Bajarilgan'; }
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

        if (task.is_creator && !['done', 'cancelled'].includes(task.status)) {
            actionsHtml += `<button class="modal-action-btn btn-danger" onclick="changeStatus(${task.id}, 'cancelled')">${IC.xmark} Vazifani bekor qilish</button>`;
        }


        actionsHtml += `
            <div class="comment-row">
                <label class="comment-attach-btn" title="Fayl biriktirish">
                    <svg class="ic" style="width:17px;height:17px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                    <input type="file" style="display:none" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.zip"
                        onchange="sendCommentWithMedia(${task.id}, this)">
                </label>
                <input type="text" class="comment-input-inline" id="comment-input-${task.id}"
                    placeholder="💬 Izoh yozing..." maxlength="1000">
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
            ? `▶️ ${formatDateTime(data.task_started_at)}`
            : '—';
        let html = `
            <div class="tc-summary">
                <div class="tc-sum-item"><span class="tc-sum-val">${data.total_hours}</span><span class="tc-sum-lab">⏱ jami soat</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.lifespan_hours}</span><span class="tc-sum-lab">📅 umumiy davomiylik</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.comments}</span><span class="tc-sum-lab">💬 izoh</span></div>
                <div class="tc-sum-item"><span class="tc-sum-val">${data.totals.attachments}</span><span class="tc-sum-lab">📎 fayl</span></div>
            </div>
            ${data.task_started_at ? `<div class="tc-started-note">⚙️ Ish boshlangan: <b>${startedLabel}</b></div>` : ''}
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
    const m = document.getElementById('task-modal');
    if (!m) return;
    m.classList.add('hidden');
    delete m.dataset.wfMode;
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
                    <option value="">Ijrochini tanlang</option>
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
            if (currentWorkspaceId !== 'personal') {
                body.company_id = currentWorkspaceId;
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
            if (currentWorkspaceId !== 'personal') {
                body.company_id = currentWorkspaceId;
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
        // Kechikkan — to'liq ko'rsatish
        const abs  = -diff;
        const days = Math.floor(abs / 86400000);
        const hrs  = Math.floor((abs % 86400000) / 3600000);
        const mins = Math.floor((abs % 3600000) / 60000);
        const secs = Math.floor((abs % 60000) / 1000);
        if (days > 0) return `${days}k ${String(hrs).padStart(2,'0')}h ${String(mins).padStart(2,'0')}m ${String(secs).padStart(2,'0')}s kechikdi`;
        if (hrs  > 0) return `${String(hrs).padStart(2,'0')}h ${String(mins).padStart(2,'0')}m ${String(secs).padStart(2,'0')}s kechikdi`;
        if (mins > 0) return `${String(mins).padStart(2,'0')}m ${String(secs).padStart(2,'0')}s kechikdi`;
        return `${String(secs).padStart(2,'0')}s kechikdi`;
    }

    // Qolgan vaqt — to'liq ko'rsatish
    const days = Math.floor(diff / 86400000);
    const hrs  = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    const secs = Math.floor((diff % 60000) / 1000);

    if (days >= 7) return `${days}k ${String(hrs).padStart(2,'0')}h qoldi`;
    if (days >  0) return `${days}k ${String(hrs).padStart(2,'0')}h ${String(mins).padStart(2,'0')}m qoldi`;
    if (hrs  >  0) return `${String(hrs).padStart(2,'0')}h ${String(mins).padStart(2,'0')}m ${String(secs).padStart(2,'0')}s qoldi`;
    if (mins >  0) return `${String(mins).padStart(2,'0')}m ${String(secs).padStart(2,'0')}s qoldi`;
    return `${String(secs).padStart(2,'0')}s qoldi`;
}

let _countdownInterval = null;
function startCountdownTicker() {
    if (_countdownInterval) clearInterval(_countdownInterval);
    _countdownInterval = setInterval(_tickCountdowns, 1000);
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
                preview = `<a href="${url}" target="_blank" class="feed-file-link">📎 ${name}</a>`;
            }
            return `
                <div class="feed-item feed-item-media">
                    <div class="feed-preview">${preview}</div>
                    <div class="feed-meta">👤 ${who} · <span class="feed-time">${when}</span></div>
                </div>`;
        } else {
            const who  = escapeHtml(item.user_name || '?');
            const when = item.created_at ? formatDateTime(item.created_at) : '';
            const txt  = escapeHtml(item.content || '');
            return `
                <div class="feed-item feed-item-comment">
                    <div class="feed-comment-bubble">
                        <div class="feed-comment-author">👤 ${who}</div>
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

    const mediaLabel = tr('app.media.title') || '📎 Mediya';
    const emptyLabel = tr('app.media.empty') || 'Mediya fayllari yo\'q';
    const uploadLabel = tr('app.media.upload') || '📤 Fayl yuklash';
    const commentPh = tr('app.media.comment_ph') || '💬 Izoh qo\'shing (ixtiyoriy)...';

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
                    <div class="mg-uploader">👤 ${byLabel}</div>
                    <div class="mg-date">📅 ${dateStr}${sizeStr ? ' · ' + sizeStr : ''}</div>
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
                <textarea id="mg-comment-${taskId}" class="mg-comment-input"
                    placeholder="${commentPh}" rows="2" maxlength="500"></textarea>
                <label class="mg-upload-btn">
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
    if (m.includes('pdf') || ext === 'pdf') return '📄';
    if (m.includes('word') || ['doc','docx'].includes(ext)) return '📝';
    if (m.includes('excel') || m.includes('spreadsheet') || ['xls','xlsx'].includes(ext)) return '📊';
    if (m.includes('powerpoint') || m.includes('presentation') || ['ppt','pptx'].includes(ext)) return '📑';
    if (m.includes('zip') || m.includes('rar') || ['zip','rar','7z'].includes(ext)) return '🗜️';
    return '📎';
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
    if (uploadBtn) uploadBtn.textContent = tr('app.media.uploading') || 'Yuklanmoqda...';

    const headers = {};
    applyAuthHeaders(headers);
    try {
        const res = await fetch(`/api/tasks/${taskId}/attachments`, { method: 'POST', body: fd, headers });
        if (!res.ok) throw new Error('upload failed');
        showToast('✅ Fayl yuklandi');
        if (commentInput) commentInput.value = '';
        input.value = '';
        // Galleryni yangilaymiz
        document.getElementById('media-gallery-modal')?.remove();
        // allTasks ni yangilaymiz
        const fresh = await apiRequest(`/tasks/${taskId}`);
        if (fresh && fresh.task) {
            const idx = allTasks.findIndex(t => t.id === taskId);
            if (idx !== -1) allTasks[idx] = { ...allTasks[idx], ...fresh.task };
        }
        openMediaGallery(taskId);
    } catch (e) {
        showToast('Yuklab bo\'lmadi', true);
        if (uploadBtn) uploadBtn.textContent = tr('app.media.upload') || '📤 Fayl yuklash';
    }
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
    urgent: { label: 'Juda muhum', icon: '🔴', cls: 'urgent', pillCls: 'hero-pill-urgent' },
    high:   { label: 'Muhum',      icon: '🟠', cls: 'high',   pillCls: 'hero-pill-high' },
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
        low: '🟢 Past', medium: '🟡 O\'rta', high: '🟠 Muhum', urgent: '🔴 Juda muhum',
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
            <div class="kmb-avatar all-icon">👥</div>
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
        filtered.forEach(t => { if (groups[t.status]) groups[t.status].push(t); });

        cols.forEach(col => {
            const el  = document.getElementById('kanban-cards-' + col);
            const list = groups[col] || [];
            _setKanbanCount(col, list.length);
            if (!el) return;

            if (!list.length) {
                const emptyMsgs = { new:'Yangi vazifa yo\'q', in_progress:'Jarayonda yo\'q', review:'Ko\'rib chiqilmoqda yo\'q', done:'Bajarilgan yo\'q' };
                const emptyIcons = { new:'📭', in_progress:'🕐', review:'🔍', done:'🎉' };
                el.innerHTML = `<div class="kanban-empty"><span class="kanban-empty-icon">${emptyIcons[col]||'📭'}</span><span>${emptyMsgs[col]||'Bo\'sh'}</span></div>`;
                return;
            }

            el.innerHTML = list.map(t => {
                const isUrgentDl = t.deadline && (new Date(t.deadline) - Date.now()) < 3600000 && t.status !== 'done';
                const dlClass = isUrgentDl ? 'kanban-card-dl kanban-card-dl-urgent' : 'kanban-card-dl';
                const dl   = t.deadline ? `<span class="${dlClass}">⏰ ${formatDateShort(t.deadline)}</span>` : '';
                const resp = t.responsible_name
                    ? `<div class="kanban-card-resp">⭐ ${escapeHtml(t.responsible_name.split(' ')[0])}</div>` : '';
                const assignees = (t.assignees || []).filter(a => !t.responsible_user_id || a.id !== t.responsible_user_id);
                const asgn = assignees.length
                    ? `<div class="kanban-card-resp" style="color:var(--text2)">👤 ${assignees.slice(0,2).map(a=>escapeHtml(a.name.split(' ')[0])).join(', ')}${assignees.length>2?' +'+( assignees.length-2):''}</div>` : '';
                const subs = (t.subtasks_count||0) > 0 ? `<div class="kanban-card-subtasks">📂 ${t.subtasks_count} sub-task</div>` : '';
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
    const headers = {};
    applyAuthHeaders(headers);
    const ws = currentWorkspace || 'all';
    const res = await fetch(`${API_BASE}/tasks?filter=all&workspace=${ws}`, { headers });
    const data = await res.json();
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
    if (!task || task.status === col) return;

    // Optimistic update
    task.status = col;
    renderKanban();
    if (tg) tg.HapticFeedback?.impactOccurred('medium');

    try {
        await apiRequest(`/tasks/${taskId}/status`, 'PATCH', { status: col });
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
    if (!task || task.status === targetCol) return;

    task.status = targetCol;
    renderKanban();
    if (tg) tg.HapticFeedback?.impactOccurred('medium');

    try {
        await apiRequest(`/tasks/${taskId}/status`, 'PATCH', { status: targetCol });
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
                        ${t.deadline ? `<span class="kanban-card-dl">⏰ ${formatDateShort(t.deadline)}</span>` : ''}
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

    const pLow    = tr('app.priority.low')    || '🟢 Past';
    const pMed    = tr('app.priority.medium') || "🟡 O'rta";
    const pHigh   = tr('app.priority.high')   || '🟠 Muhum';
    const pUrgent = tr('app.priority.urgent') || '🔴 Juda muhum';

    const membersHtml = members.length ? members.map(m => {
        const sel = _stAssigneeIds.includes(m.id);
        const init = (m.name || '?')[0].toUpperCase();
        return `<div class="assignee-chip ${sel ? 'selected' : ''}" id="stchip-${m.id}" onclick="_stToggleAssignee(${m.id},this)">
            <span class="assignee-avatar">${escapeHtml(init)}</span>
            <span class="assignee-name">👤 ${escapeHtml(m.name)}${m.is_self?' (siz)':''}</span>
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
                        📅 <span id="st-dl-label">Sana tanlang...</span>
                    </button>
                    <button onclick="_stClearDeadline()" style="background:none;border:none;color:var(--text3);font-size:20px;cursor:pointer;padding:4px">✕</button>
                </div>
                <input type="hidden" id="st-deadline">
            </div>

            ${members.length ? `<div class="form-group" style="margin-bottom:14px">
                <label class="form-label">👥 Ijrochilar</label>
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
            html += `<div class="cmp-action-title" style="margin-bottom:8px">🏢 Bot jamoalari</div>`;
            html += workspaces.map(w => {
                const isOwner = w.is_owner;
                const isAdmin = w.is_admin || isOwner;
                const roleLabel = isOwner ? '👑 Owner' : (isAdmin ? '🛡 Admin' : '👤 A\'zo');
                const roleClass = isOwner ? 'owner' : '';
                return `
                    <div class="company-card" onclick="openCompanyDetail(${w.id},'${escapeHtml(w.name)}',${isAdmin})">
                        <div class="company-card-row">
                            <span class="company-card-name">🏢 ${escapeHtml(w.name)}</span>
                            <span class="company-card-role ${roleClass}">${roleLabel}</span>
                        </div>
                        <div class="company-card-meta">${w.member_count || ''} a'zo • <span class="team-type-badge bot">bot</span></div>
                    </div>
                `;
            }).join('');
        }

        // Telegram guruhlar section
        if (groups.length) {
            html += `<div class="cmp-action-title" style="margin:16px 0 8px">💬 Telegram guruhlar</div>`;
            html += groups.map(g => {
                return `
                    <div class="company-card" onclick="openCompanyDetail(${g.id},'${escapeHtml(g.title || g.name)}',false)">
                        <div class="company-card-row">
                            <span class="company-card-name">💬 ${escapeHtml(g.title || g.name)}</span>
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
                <div class="cmp-action-title">👑 Owner imkoniyatlari</div>
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
        const roleLabel = m.is_owner ? '👑 Owner' : (m.role === 'admin' ? '🛡 Admin' : '👤 A\'zo');
        const canEdit = isAdmin && !m.is_self && !m.is_owner;
        const canRole = isAdmin && !m.is_self && !m.is_owner;
        const actionsHtml = canEdit ? `
            <div class="member-edit-actions" style="display:none">
                <button class="member-role-btn" onclick="openRoleSheet(${companyId},${m.id},'${escapeHtml(m.name)}','${m.role||'member'}')">
                    👑 Rol
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
        { value: 'admin',  icon: '🛡', label: 'Admin',     desc: 'Jamoa boshqarish, a\'zo qo\'shish/chiqarish huquqi' },
        { value: 'member', icon: '👤', label: 'A\'zo',     desc: 'Odatiy foydalanuvchi, faqat o\'z vazifalari' },
    ];

    const overlay = document.createElement('div');
    overlay.id = 'role-sheet-overlay';
    overlay.className = 'gp-overlay';
    overlay.innerHTML = `
        <div class="gp-sheet">
            <div class="gp-sheet-header">
                <span class="gp-sheet-title">👑 ${escapeHtml(userName)} — Rol tanlash</span>
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
    if (tg) tg.HapticFeedback?.impactOccurred('light');
}

function closeSettingsPanel() {
    const panel = document.getElementById('settings-panel');
    if (!panel) return;
    panel.classList.remove('open');
    setTimeout(() => panel.classList.add('hidden'), 300);
}

