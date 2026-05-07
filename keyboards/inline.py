"""
Inline klaviaturalar - barcha tugmalar
"""
from typing import List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.models import Task, TaskStatus, Priority, User, UserRole
from i18n import t


def language_keyboard(back_target: str = "menu:main") -> InlineKeyboardMarkup:
    """Til tanlash klaviaturasi — har bir tugma tanlangan tildan keyin
    qaytadigan menyuni ko'rsatadi (back_target callback)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇿 O'zbek", callback_data="lang:uz")
    builder.button(text="🇷🇺 Русский", callback_data="lang:ru")
    builder.button(text="🇬🇧 English", callback_data="lang:en")
    builder.button(text="🔙 / Back / Назад", callback_data=back_target)
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    """Asosiy menyu — tanlangan tilda. Bot va mini-app funksiyalari ikkalasi
    ham qulay bo'lishi uchun barcha asosiy bo'limlar bor."""
    builder = InlineKeyboardBuilder()

    if settings.WEBAPP_URL:
        builder.row(InlineKeyboardButton(
            text=t("menu.open_app", lang),
            web_app=WebAppInfo(url=f"{settings.WEBAPP_URL.rstrip('/')}/?v=67"),
        ))

    builder.button(text=t("menu.newtask", lang), callback_data="menu:newtask")
    builder.button(text=t("menu.mytasks", lang), callback_data="menu:mytasks")
    builder.button(text=t("menu.stats", lang), callback_data="menu:stats")
    builder.button(text=t("menu.overdue", lang), callback_data="menu:overdue")
    builder.button(text=t("menu.companies", lang), callback_data="menu:companies")
    builder.button(text=t("menu.groups", lang), callback_data="menu:groups")
    builder.button(text="📨 Taklif havolasi", callback_data="menu:invite")
    builder.button(text=t("menu.settings", lang), callback_data="menu:settings")

    # WebApp + 2x2 + 2 + 1 + 1
    builder.adjust(1, 2, 2, 2, 1, 1)
    return builder.as_markup()


def stats_workspace_keyboard(companies: list) -> InlineKeyboardMarkup:
    """Stats: workspace tanlash"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Shaxsiy statistika", callback_data="stats:personal")
    for c in companies:
        builder.button(text=f"🏢 {c['name']}", callback_data=f"stats:co:{c['id']}")
    builder.button(text="🔙 Orqaga", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def leaderboard_keyboard(member_stats: list, company_id: int) -> InlineKeyboardMarkup:
    """Team leaderboard: click member to see their dashboard"""
    MEDALS = ["🥇", "🥈", "🥉"] + ["👤"] * 20
    builder = InlineKeyboardBuilder()
    for i, m in enumerate(member_stats[:8]):
        medal = MEDALS[i]
        text  = f"{medal} {m['user_name'][:22]}  ⭐{m['score']}"
        builder.button(text=text,
                       callback_data=f"stats:member:{m['user_id']}:{company_id}")
    builder.button(text="🔙 Orqaga", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def priority_keyboard() -> InlineKeyboardMarkup:
    """Muhimlik darajasini tanlash"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 Past", callback_data="priority:low")
    builder.button(text="🟡 O'rta", callback_data="priority:medium")
    builder.button(text="🟠 Muhum", callback_data="priority:high")
    builder.button(text="🔴 Juda muhum", callback_data="priority:urgent")
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def deadline_keyboard() -> InlineKeyboardMarkup:
    """Deadline tanlash - tez variantlar"""
    _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
    now = datetime.now(_TZ)
    builder = InlineKeyboardBuilder()
    
    today_evening = now.replace(hour=18, minute=0)
    if today_evening > now:
        builder.button(text="🕕 Bugun 18:00", callback_data=f"deadline:{today_evening.timestamp():.0f}")
    
    tomorrow = (now + timedelta(days=1)).replace(hour=18, minute=0)
    builder.button(text="📅 Ertaga 18:00", callback_data=f"deadline:{tomorrow.timestamp():.0f}")
    
    in_3_days = (now + timedelta(days=3)).replace(hour=18, minute=0)
    builder.button(text="📆 3 kundan keyin", callback_data=f"deadline:{in_3_days.timestamp():.0f}")
    
    in_week = (now + timedelta(days=7)).replace(hour=18, minute=0)
    builder.button(text="🗓 Bir haftadan keyin", callback_data=f"deadline:{in_week.timestamp():.0f}")
    
    builder.button(text="✏️ Qo'lda kiritish", callback_data="deadline:custom")
    builder.button(text="⏭ Deadline yo'q", callback_data="deadline:none")
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def assignee_keyboard(members: List, include_self: bool = True) -> InlineKeyboardMarkup:
    """Ijrochi tanlash klaviaturasi"""
    builder = InlineKeyboardBuilder()
    for member in members:
        user = member.user if hasattr(member, 'user') else member
        builder.button(
            text=f"👤 {user.full_name}",
            callback_data=f"assignee:{user.id}"
        )
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def multi_assignee_keyboard(
    members: List,
    selected_ids: Optional[List[int]] = None,
    external: Optional[List[dict]] = None,   # [{id, name}]
) -> InlineKeyboardMarkup:
    """Bir nechta ijrochi tanlash (toggle) + boshqa guruhdan qo'shish"""
    selected = set(selected_ids or [])
    all_ext = external or []
    ext_ids = {e["id"] for e in all_ext}
    builder = InlineKeyboardBuilder()

    # Asosiy guruh a'zolari
    for member in members:
        u = member.user if hasattr(member, 'user') else member
        mark = "✅ " if u.id in selected else "☐ "
        builder.button(text=f"{mark}{u.full_name}", callback_data=f"assign_toggle:{u.id}")

    # Tashqi guruhdan qo'shilganlar
    for ext in all_ext:
        builder.button(
            text=f"✅ {ext['name']} 🔗",
            callback_data=f"assign_toggle_ext:{ext['id']}",
        )

    builder.button(text="➕ Boshqa guruhdan qo'shish", callback_data="afg")
    builder.button(text="✔️ Tayyor", callback_data="assign_done")
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def group_picker_keyboard(companies: List, groups: List, exclude_company_id=None) -> InlineKeyboardMarkup:
    """Boshqa guruh/kompaniyani tanlash klaviaturasi"""
    builder = InlineKeyboardBuilder()
    for c in companies:
        if exclude_company_id and c.id == exclude_company_id:
            continue
        builder.button(text=f"🏢 {c.name}", callback_data=f"afg_c:{c.id}")
    for g in groups:
        builder.button(text=f"👥 {g.name}", callback_data=f"afg_g:{g.id}")
    builder.button(text="📨 Taklif havolasi yuborish", callback_data="afg_invite")
    builder.button(text="‹ Orqaga", callback_data="afg_back")
    builder.adjust(1)
    return builder.as_markup()


def ext_members_keyboard(members: List, already_ids: set) -> InlineKeyboardMarkup:
    """Tashqi guruh a'zolarini ko'rsatish"""
    builder = InlineKeyboardBuilder()
    for member in members:
        u = member.user if hasattr(member, 'user') else member
        if u.id in already_ids:
            builder.button(text=f"✅ {u.full_name}", callback_data=f"afg_noop")
        else:
            builder.button(text=f"➕ {u.full_name}", callback_data=f"afg_add:{u.id}")
    builder.button(text="‹ Orqaga", callback_data="afg_back")
    builder.adjust(1)
    return builder.as_markup()


def workspace_picker_keyboard(companies: List, groups: List) -> InlineKeyboardMarkup:
    """Vazifa qayerda yaratilishini tanlash: Shaxsiy / Jamoa / Guruh"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Shaxsiy vazifa", callback_data="ws:personal")
    for c in companies:
        builder.button(text=f"🏢 {c.name} (Jamoa)", callback_data=f"ws:company:{c.id}")
    for g in groups:
        builder.button(text=f"👥 {g.name}", callback_data=f"ws:group:{g.id}")
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def task_actions_keyboard(
    task: Task,
    user_role: UserRole,
    is_assignee: bool = False,
    user_assignment=None,   # TaskAssignment | None
) -> InlineKeyboardMarkup:
    """Vazifa amallari - rolga qarab tugmalar.

    Statusni o'zgartirish huquqi FAQAT masul (is_responsible=True) ijrochilarda.
    Har bir masul ijrochi faqat O'Z shaxsiy statusini o'zgartiradi:
      new → in_progress  (▶️ Ishga kirishish)
      in_progress → done (✅ Bajarildi)
    Barcha masul ijrochilar 'done' belgilasa — vazifa avtomatik yakunlanadi.
    """
    builder = InlineKeyboardBuilder()

    # --- Shaxsiy status tugmalari (faqat masul ijrochilar uchun) ---
    if user_assignment and user_assignment.is_responsible:
        assign_status = user_assignment.status or "new"
        if task.status not in (TaskStatus.DONE, TaskStatus.CANCELLED):
            if assign_status == "new":
                builder.button(
                    text="▶️ Ishga kirishish",
                    callback_data=f"my_assign_status:{task.id}:in_progress",
                )
            elif assign_status == "in_progress":
                builder.button(
                    text="✅ Bajarildi deb belgilash",
                    callback_data=f"my_assign_status:{task.id}:done",
                )
            elif assign_status == "done":
                builder.button(
                    text="↩️ Qayta ochish",
                    callback_data=f"my_assign_status:{task.id}:in_progress",
                )

    # Admin/Manager: vazifani majburiy yakunlash yoki bekor qilish
    if user_role in (UserRole.ADMIN, UserRole.MANAGER):
        if task.status not in (TaskStatus.DONE, TaskStatus.CANCELLED):
            builder.button(
                text="⛔ Bekor qilish",
                callback_data=f"task_status:{task.id}:cancelled",
            )
        if task.status == TaskStatus.DONE:
            builder.button(
                text="🔄 Qayta ochish",
                callback_data=f"task_status:{task.id}:in_progress",
            )

    builder.button(text="💬 Izohlar", callback_data=f"task_comments:{task.id}")
    builder.button(text="📝 Tarix", callback_data=f"task_history:{task.id}")

    # Mediya tugmasi — faqat attachmentlar bo'lsa ko'rsatiladi
    if task.attachments:
        media_count = len(task.attachments)
        builder.button(
            text=f"🖼 Mediya ({media_count})",
            callback_data=f"task_media:{task.id}",
        )

    # Sub-task tugmalari
    if task.subtasks:
        builder.button(
            text=f"📂 Sub-tasklar ({len(task.subtasks)})",
            callback_data=f"subtask_list:{task.id}",
        )
    if user_role in (UserRole.ADMIN, UserRole.MANAGER) and not task.parent_id:
        builder.button(text="📂➕ Sub-task qo'shish", callback_data=f"subtask_add:{task.id}")

    if user_role in (UserRole.ADMIN, UserRole.MANAGER):
        builder.button(text="✏️ Tahrirlash", callback_data=f"task_edit:{task.id}")
        builder.button(text="🗑 O'chirish", callback_data=f"task_delete:{task.id}")

    builder.button(text="🔙 Orqaga", callback_data="menu:mytasks")
    builder.adjust(2)
    return builder.as_markup()


def confirm_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Tasdiqlash klaviaturasi"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, tasdiqlayman", callback_data=f"confirm:{action}:{item_id}")
    builder.button(text="❌ Yo'q, bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def task_list_keyboard(tasks: List[Task], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Vazifalar ro'yxati paginatsiya bilan"""
    builder = InlineKeyboardBuilder()
    
    start = page * per_page
    end = start + per_page
    page_tasks = tasks[start:end]
    
    for task in page_tasks:
        emoji = {
            TaskStatus.NEW: "🆕",
            TaskStatus.IN_PROGRESS: "⚙️",
            TaskStatus.REVIEW: "🔍",
            TaskStatus.DONE: "✅",
            TaskStatus.OVERDUE: "⏰",
            TaskStatus.CANCELLED: "🚫",
        }.get(task.status, "📌")
        
        title = task.title[:40] + "..." if len(task.title) > 40 else task.title
        builder.button(
            text=f"{emoji} {title}",
            callback_data=f"task_view:{task.id}"
        )
    
    builder.adjust(1)
    
    total_pages = (len(tasks) - 1) // per_page + 1
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="◀️", callback_data=f"tasks_page:{page-1}")
            )
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="▶️", callback_data=f"tasks_page:{page+1}")
            )
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 Menyu", callback_data="menu:main"))
    return builder.as_markup()


def filter_tasks_keyboard() -> InlineKeyboardMarkup:
    """Vazifalarni filtrlash"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Yangi", callback_data="filter:new")
    builder.button(text="⚙️ Jarayonda", callback_data="filter:in_progress")
    builder.button(text="🔍 Ko'rib chiqilmoqda", callback_data="filter:review")
    builder.button(text="✅ Bajarilgan", callback_data="filter:done")
    builder.button(text="⏰ Kechikkan", callback_data="filter:overdue")
    builder.button(text="📋 Barchasi", callback_data="filter:all")
    builder.button(text="🔙 Orqaga", callback_data="menu:main")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def group_admin_keyboard(group_id: int) -> InlineKeyboardMarkup:
    """Guruh admin paneli"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 A'zolar", callback_data=f"group_members:{group_id}")
    builder.button(text="📊 Statistika", callback_data=f"group_stats:{group_id}")
    builder.button(text="📋 Vazifalar", callback_data=f"group_tasks:{group_id}")
    builder.button(text="⚙️ Sozlamalar", callback_data=f"group_settings:{group_id}")
    builder.button(text="📑 Hisobot", callback_data=f"group_report:{group_id}")
    builder.button(text="🔙 Orqaga", callback_data="menu:groups")
    builder.adjust(2)
    return builder.as_markup()


def settings_keyboard(user: User) -> InlineKeyboardMarkup:
    """Foydalanuvchi sozlamalari — tanlangan tilda."""
    lang = user.language
    builder = InlineKeyboardBuilder()

    notif_key = "settings.btn.notif_on" if user.notifications_enabled else "settings.btn.notif_off"
    builder.button(text=t(notif_key, lang), callback_data="settings:toggle_notif")

    lang_emoji = {"uz": "🇺🇿", "ru": "🇷🇺", "en": "🇬🇧"}.get(lang, "🌐")
    builder.button(
        text=t("settings.btn.language", lang, flag=lang_emoji, code=lang.upper()),
        callback_data="settings:language",
    )

    builder.button(text=t("settings.btn.timezone", lang), callback_data="settings:timezone")
    builder.button(text=t("settings.btn.export", lang), callback_data="settings:export")
    builder.button(text=t("common.back_to_menu", lang), callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Faqat bekor qilish tugmasi"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Menyu ga qaytish"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Asosiy menyu", callback_data="menu:main")
    return builder.as_markup()
