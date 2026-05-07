"""
Yordamchi funksiyalar
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from database.models import TaskStatus, Priority
from config import settings

_TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)


STATUS_EMOJI = {
    TaskStatus.NEW: "🆕",
    TaskStatus.IN_PROGRESS: "⚙️",
    TaskStatus.REVIEW: "🔍",
    TaskStatus.DONE: "✅",
    TaskStatus.OVERDUE: "⏰",
    TaskStatus.CANCELLED: "🚫",
}

STATUS_NAMES_UZ = {
    TaskStatus.NEW: "Yangi",
    TaskStatus.IN_PROGRESS: "Jarayonda",
    TaskStatus.REVIEW: "Ko'rib chiqilmoqda",
    TaskStatus.DONE: "Bajarildi",
    TaskStatus.OVERDUE: "Kechikdi",
    TaskStatus.CANCELLED: "Bekor qilindi",
}

PRIORITY_EMOJI = {
    Priority.LOW: "🟢",
    Priority.MEDIUM: "🟡",
    Priority.HIGH: "🟠",
    Priority.URGENT: "🔴",
}

PRIORITY_NAMES_UZ = {
    Priority.LOW: "Past",
    Priority.MEDIUM: "O'rta",
    Priority.HIGH: "Yuqori",
    Priority.URGENT: "Juda muhim",
}


def format_deadline(deadline: Optional[datetime]) -> str:
    """Deadline ni chiroyli formatda ko'rsatish"""
    if not deadline:
        return "Belgilanmagan"
    
    now = datetime.now(_TZ)
    
    # Ensure deadline is timezone-aware for comparison
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=_TZ)
    else:
        deadline = deadline.astimezone(_TZ)
    
    diff = deadline - now
    
    if diff.total_seconds() < 0:
        hours_late = abs(diff.total_seconds()) / 3600
        if hours_late < 24:
            return f"⛔ {int(hours_late)} soat kechikdi"
        days_late = int(hours_late / 24)
        return f"⛔ {days_late} kun kechikdi"
    
    if diff.days == 0:
        hours = int(diff.total_seconds() / 3600)
        if hours < 1:
            return f"🚨 Bugun - 1 soatdan kam!"
        return f"🔴 Bugun ({hours} soat qoldi)"
    
    if diff.days == 1:
        return f"🟡 Ertaga ({deadline.strftime('%H:%M')})"
    
    if diff.days < 7:
        return f"🟢 {diff.days} kun qoldi"
    
    return f"📅 {deadline.strftime('%d.%m.%Y %H:%M')}"


def format_task_short(task) -> str:
    """Qisqa vazifa ma'lumoti"""
    emoji = STATUS_EMOJI.get(task.status, "📌")
    priority = PRIORITY_EMOJI.get(task.priority, "")
    title = task.title[:50] + "..." if len(task.title) > 50 else task.title
    
    line = f"{emoji} {priority} <b>{title}</b>"
    if task.deadline:
        line += f"\n   {format_deadline(task.deadline)}"
    return line


def format_task_detailed(task) -> str:
    """Batafsil vazifa ma'lumoti"""
    emoji = STATUS_EMOJI.get(task.status, "📌")
    priority = PRIORITY_EMOJI.get(task.priority, "")
    status_name = STATUS_NAMES_UZ.get(task.status, task.status.value)
    priority_name = PRIORITY_NAMES_UZ.get(task.priority, task.priority.value)
    
    text = f"{emoji} <b>{task.title}</b>\n\n"
    
    if task.description:
        text += f"📄 <b>Tavsif:</b>\n{task.description}\n\n"
    
    text += f"📊 <b>Status:</b> {status_name}\n"
    text += f"{priority} <b>Muhimlik:</b> {priority_name}\n"
    
    if task.deadline:
        text += f"⏰ <b>Deadline:</b> {format_deadline(task.deadline)}\n"
    
    if hasattr(task, 'creator') and task.creator:
        text += f"👤 <b>Yaratgan:</b> {task.creator.full_name}\n"
    
    if hasattr(task, 'assignments') and task.assignments:
        # Shaxsiy status emoji xaritasi
        _ASGN_STATUS = {
            "new":         "🆕",
            "in_progress": "⚙️",
            "done":        "✅",
        }
        resp_list  = [a for a in task.assignments if a.is_responsible and a.user]
        other_list = [a for a in task.assignments if not a.is_responsible and a.user]

        if resp_list:
            lines = []
            for a in resp_list:
                st_em = _ASGN_STATUS.get(a.status or "new", "🆕")
                lines.append(f"{st_em} {a.user.full_name}")
            text += f"⭐ <b>Masul ijrochilar:</b>\n" + "\n".join(f"   {l}" for l in lines) + "\n"

        if other_list:
            names = [a.user.full_name for a in other_list]
            text += f"👥 <b>Ishtrokchilar:</b> {', '.join(names)}\n"
        elif not resp_list and task.assignments:
            # is_responsible belgilanmagan — hammasini ko'rsatamiz
            lines = []
            for a in task.assignments:
                if a.user:
                    st_em = _ASGN_STATUS.get(a.status or "new", "🆕")
                    lines.append(f"{st_em} {a.user.full_name}")
            text += f"👥 <b>Ijrochilar:</b>\n" + "\n".join(f"   {l}" for l in lines) + "\n"

    if hasattr(task, 'subtasks') and task.subtasks:
        done_sub = sum(1 for s in task.subtasks if s.status == TaskStatus.DONE)
        total_sub = len(task.subtasks)
        text += f"📂 <b>Sub-tasklar:</b> {done_sub}/{total_sub} bajarildi\n"

    if hasattr(task, 'attachments') and task.attachments:
        type_emoji = {"photo": "🖼", "video": "🎥", "document": "📄",
                      "audio": "🎵", "voice": "🎙"}
        text += f"\n📎 <b>Biriktirilgan fayllar ({len(task.attachments)}):</b>\n"
        for a in task.attachments[:10]:
            em = type_emoji.get(a.file_type, "📎")
            nm = a.file_name or a.file_type
            text += f"   {em} {nm}\n"

    text += f"\n🕐 <b>Yaratildi:</b> {task.created_at.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}"
    
    if task.completed_at:
        text += f"\n✅ <b>Bajarildi:</b> {task.completed_at.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}"
    
    return text


def parse_datetime(text: str) -> Optional[datetime]:
    """Matndan sanani olish"""
    formats = [
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    
    text = text.strip()
    
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                dt = dt.replace(hour=18, minute=0)
            return dt.replace(tzinfo=_TZ)
        except ValueError:
            continue
    
    return None


def chunk_list(items: list, chunk_size: int) -> list:
    """Ro'yxatni bo'laklarga bo'lish"""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
