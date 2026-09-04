"""
Notification service - bildirishnomalar yuborish
"""
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

_UTC = ZoneInfo("UTC")
_TZ = ZoneInfo("Asia/Tashkent")

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Notification, NotificationType, User, Task

logger = logging.getLogger(__name__)

# Muhimlik darajalarini o'zbekchaga tarjima qilish
_PRIO_UZ = {
    "low":    "Past",
    "medium": "O'rta",
    "high":   "Yuqori",
    "urgent": "Juda muhim",
}


class NotificationService:
    """Bildirishnomalar yuborish xizmati"""
    
    @staticmethod
    async def send_notification(
        bot: Bot,
        session: AsyncSession,
        user_id: int,
        notification_type: NotificationType,
        message: str,
        task_id: Optional[int] = None,
        reply_markup=None,
    ) -> bool:
        """Foydalanuvchiga bildirishnoma yuborish"""
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user or not user.notifications_enabled or user.is_banned:
            return False

        notification = Notification(
            user_id=user_id,
            type=notification_type,
            message=message,
            task_id=task_id,
        )
        session.add(notification)

        # Task uchun avtomatik tugma — Mini App da ochish
        if task_id and reply_markup is None:
            try:
                from config import settings as _cfg
                from aiogram.types import (
                    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
                )
                kb_rows = []
                if _cfg.WEBAPP_URL:
                    kb_rows.append([InlineKeyboardButton(
                        text="📱 Mini app da ochish",
                        web_app=WebAppInfo(url=_cfg.WEBAPP_URL),
                    )])
                kb_rows.append([InlineKeyboardButton(
                    text="📋 Tafsilotlar", callback_data=f"view_task:{task_id}",
                )])
                reply_markup = InlineKeyboardMarkup(inline_keyboard=kb_rows)
            except Exception:
                pass

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return True
        except TelegramForbiddenError:
            # Foydalanuvchi botni o'zi blokladi/o'chirdi — bu admin ban EMAS!
            # is_banned'ni o'zgartirmaymiz (aks holda guruhda admin ban kabi
            # qabul qilinadi va u qayta ulansa ham noto'g'ri belgilangan qoladi).
            logger.warning(f"Foydalanuvchi {user.telegram_id} botni blokladi (avtomatik ban qo'yilmadi)")
            return False
        except TelegramBadRequest as e:
            logger.error(f"Xato yuborishda {user.telegram_id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Kutilmagan xato: {e}")
            return False
    
    @staticmethod
    async def notify_task_assigned(
        bot: Bot,
        session: AsyncSession,
        task: Task,
        assignee_ids: List[int],
        responsible_user_id: Optional[int] = None,
        responsible_user_ids: Optional[List[int]] = None,
    ) -> None:
        """Vazifa biriktirilgani haqida xabar — masulga boshqacha xabar"""
        # responsible_user_ids ustunlik oladi
        resp_set: set = set(responsible_user_ids or [])
        if responsible_user_id and not resp_set:
            resp_set = {responsible_user_id}

        deadline_text = ""
        if task.deadline:
            deadline_text = f"\n⏰ <b>Deadline:</b> {task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}"

        priority_emoji = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"
        }.get(task.priority.value, "⚪")

        for user_id in assignee_ids:
            is_resp = user_id in resp_set
            if is_resp:
                message = (
                    f"⭐ <b>Siz bu vazifada MAS'UL sifatida belgilandingiz!</b>\n\n"
                    f"📝 <b>Nomi:</b> {task.title}\n"
                    f"{priority_emoji} <b>Muhimlik:</b> {_PRIO_UZ.get(task.priority.value, task.priority.value)}"
                    f"{deadline_text}\n\n"
                    f"Vazifaning bajarilishini nazorat qiling va jamoangizga yordam bering."
                )
            else:
                message = (
                    f"📌 <b>Sizga yangi vazifa biriktirildi!</b>\n\n"
                    f"📝 <b>Nomi:</b> {task.title}\n"
                    f"{priority_emoji} <b>Muhimlik:</b> {_PRIO_UZ.get(task.priority.value, task.priority.value)}"
                    f"{deadline_text}"
                )
            await NotificationService.send_notification(
                bot, session, user_id,
                NotificationType.TASK_ASSIGNED,
                message, task.id,
            )
    
    @staticmethod
    def _format_time_left(deadline: datetime) -> tuple[str, str, str]:
        """
        Qolgan vaqtni aniq hisoblaydi.
        Returns: (emoji, urgency_text, notif_type_key)
        notif_type_key: 'morning' | 'warning' | 'urgent' | 'exact'
        """
        now = datetime.now(_UTC)
        # Deadline TZ-aware bo'lsa, solishtirish uchun hар ikkalasini UTC ga o'tkazamiz
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=_UTC)
        diff = deadline - now
        total_sec = int(diff.total_seconds())

        if total_sec <= 0:
            return "🔴", "Vaqt tugadi!", "exact"

        minutes = total_sec // 60
        hours   = minutes // 60
        mins    = minutes % 60
        days    = hours // 24
        hrs     = hours % 24

        if days >= 1:
            time_str = f"{days} kun" + (f" {hrs} soat" if hrs else "")
            return "📅", f"⏳ {time_str} qoldi", "morning"
        elif hours >= 3:
            time_str = f"{hours} soat" + (f" {mins} daqiqa" if mins else "")
            return "⚠️", f"⏳ {time_str} qoldi", "warning"
        elif hours >= 1:
            time_str = f"{hours} soat" + (f" {mins} daqiqa" if mins else "")
            return "🚨", f"⏳ {time_str} qoldi — SHOSHILING!", "urgent"
        else:
            return "🔴", f"⏳ {minutes} daqiqa qoldi — TEZKOR!", "urgent"

    @staticmethod
    async def notify_deadline_warning(
        bot: Bot,
        session: AsyncSession,
        task: Task,
        hours_left: int = 0,   # endi faqat compat uchun saqlanib qoldi
    ) -> None:
        """Deadline yaqinlashgani haqida — aniq qolgan vaqt bilan"""
        emoji, urgency, type_key = NotificationService._format_time_left(task.deadline)

        notif_type = (
            NotificationType.DEADLINE_URGENT
            if type_key in ("urgent", "exact")
            else NotificationType.DEADLINE_WARNING
        )

        priority_emoji = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"
        }.get(
            task.priority.value if hasattr(task.priority, 'value') else str(task.priority),
            "⚪"
        )

        message = (
            f"{emoji} <b>Deadline eslatmasi</b>\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"{priority_emoji} Muhimlik: "
            f"{task.priority.value if hasattr(task.priority, 'value') else task.priority}\n"
            f"⏰ Deadline: {task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>{urgency}</b>\n\n"
            f"Tezroq harakat qiling! /task_{task.id}"
        )

        # Mas'ul (responsible) ijrochilar: "vazifangiz deadline yaqin" deb to'g'ridan-to'g'ri yuboramiz.
        # Yaratuvchi (creator): agar mas'ul emas bo'lsa, alohida informatsiya xabari (kim kechikishi
        # mumkinligini bildiramiz). Kuzatuvchilar (observer) hech narsa olmaydi.
        responsible = [a for a in task.assignments if a.is_responsible]
        active_resp = [a for a in responsible if (a.status or "new") not in ("done", "cancelled")]

        # 1) Mas'ul ijrochilarga aksiyali xabar (yuqoridagi "message")
        for a in active_resp:
            await NotificationService.send_notification(
                bot, session, a.user_id, notif_type, message, task.id,
            )

        # 2) Yaratuvchi (mas'ul emas, kuzatuvchi/yaratuvchi sifatida) — informatsion xabar
        creator_is_resp = any(a.user_id == task.creator_id and a.is_responsible for a in task.assignments)
        if not creator_is_resp and task.creator_id and active_resp:
            from database.models import User as _User
            resp_names = []
            for a in active_resp:
                u = await session.get(_User, a.user_id)
                if u:
                    resp_names.append(f"@{u.username}" if u.username else u.full_name)
            resp_str = ", ".join(resp_names) if resp_names else "—"
            info_msg = (
                f"⏰ <b>Yaratgan vazifangizning muddati yaqin</b>\n\n"
                f"📌 <b>{task.title}</b>\n"
                f"{priority_emoji} Muhimlik: "
                f"{task.priority.value if hasattr(task.priority, 'value') else task.priority}\n"
                f"⏰ Deadline: {task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}\n"
                f"<b>{urgency}</b>\n\n"
                f"👤 Mas'ul: <b>{resp_str}</b>\n"
                f"<i>(Sizga ma'lumot uchun — choralarni mas'ul ko'radi.)</i>\n\n"
                f"Batafsil: /task_{task.id}"
            )
            await NotificationService.send_notification(
                bot, session, task.creator_id, notif_type, info_msg, task.id,
            )

    @staticmethod
    async def notify_step_deadline_warning(
        bot: Bot,
        session: AsyncSession,
        step,   # TaskStep
        label: str = "",   # 'morning' | '3h' | '2h' | '1h' | 'exact'
    ) -> None:
        """Workflow qadam deadline eslatmasi — ijrochiga"""
        if not step.deadline:
            return

        emoji, urgency, _ = NotificationService._format_time_left(step.deadline)

        message = (
            f"{emoji} <b>Workflow qadam eslatmasi</b>\n\n"
            f"📋 <b>{step.title}</b>\n"
            f"⏰ Deadline: {step.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>{urgency}</b>\n\n"
            f"Vazifani ko'rish: /task_{step.task_id}"
        )

        await NotificationService.send_notification(
            bot, session, step.assignee_user_id,
            NotificationType.DEADLINE_WARNING,
            message, step.task_id,
        )
    
    @staticmethod
    async def notify_task_overdue(
        bot: Bot,
        session: AsyncSession,
        task: Task,
    ) -> None:
        """Vazifa kechikkani haqida"""
        message = (
            f"🚨 <b>Vazifa kechikdi!</b>\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"⏰ Deadline edi: {task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Darhol harakat qiling: /task_{task.id}"
        )
        
        # MAS'UL ijrochilarga "vazifangiz kechikdi" deb harakat xabari,
        # YARATUVCHIga "vazifa kechikyapti, mas'ul X kechikdi" deb info xabari.
        # Kuzatuvchilar bezovta qilinmaydi.
        responsible = [a for a in task.assignments if a.is_responsible]
        active_resp = [a for a in responsible if (a.status or "new") not in ("done", "cancelled")]

        # 1) Mas'ul ijrochilarga aksiyali xabar
        for a in active_resp:
            await NotificationService.send_notification(
                bot, session, a.user_id,
                NotificationType.TASK_OVERDUE,
                message, task.id,
            )

        # 2) Yaratuvchi (mas'ul emas) — kim kechikayotganini ko'rsatamiz
        creator_is_resp = any(a.user_id == task.creator_id and a.is_responsible for a in task.assignments)
        if not creator_is_resp and task.creator_id and active_resp:
            from database.models import User as _User
            late_names = []
            for a in active_resp:
                u = await session.get(_User, a.user_id)
                if u:
                    late_names.append(f"@{u.username}" if u.username else u.full_name)
            late_str = ", ".join(late_names) if late_names else "—"
            info_msg = (
                f"⏰ <b>Yaratgan vazifangiz kechikdi</b>\n\n"
                f"📌 <b>{task.title}</b>\n"
                f"⏰ Deadline edi: {task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}\n\n"
                f"👤 Kechikayotgan mas'ul: <b>{late_str}</b>\n\n"
                f"Vazifani ko'rish: /task_{task.id}"
            )
            await NotificationService.send_notification(
                bot, session, task.creator_id,
                NotificationType.TASK_OVERDUE,
                info_msg, task.id,
            )
    
    @staticmethod
    async def notify_status_changed(
        bot: Bot,
        session: AsyncSession,
        task: Task,
        old_status: str,
        new_status: str,
        changed_by_name: str,
        recipient_ids: Optional[set] = None,
    ) -> None:
        """Umumiy task statusi o'zgarganini xabar qilish"""
        status_names = {
            "new": "🆕 Yangi", "in_progress": "⚙️ Jarayonda",
            "review": "🔍 Ko'rib chiqilmoqda", "done": "✅ Bajarildi",
            "overdue": "⏰ Kechikdi", "cancelled": "🚫 Bekor qilindi",
        }

        message = (
            f"🔄 <b>Vazifa statusi o'zgardi</b>\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"{status_names.get(old_status, old_status)} ➡️ {status_names.get(new_status, new_status)}\n"
            f"👤 O'zgartirdi: {changed_by_name}\n\n"
            f"Batafsil: /task_{task.id}"
        )

        if recipient_ids is None:
            recipient_ids = {task.creator_id}
            for assignment in task.assignments:
                recipient_ids.add(assignment.user_id)

        for user_id in recipient_ids:
            await NotificationService.send_notification(
                bot, session, user_id,
                NotificationType.TASK_STATUS_CHANGED,
                message, task.id,
            )

    @staticmethod
    async def notify_my_status_changed(
        bot: Bot,
        session: AsyncSession,
        task: Task,
        new_status: str,
        changed_by_name: str,
        recipient_ids: Optional[set] = None,
    ) -> None:
        """Ijrochining shaxsiy statusi o'zgarganini xabar qilish"""
        status_names = {
            "new": "🆕 Yangi", "in_progress": "⚙️ Jarayonda",
            "review": "🔍 Ko'rib chiqilmoqda", "done": "✅ Bajarildi",
            "overdue": "⏰ Kechikdi", "cancelled": "🚫 Bekor qilindi",
        }

        status_emoji = {
            "in_progress": "▶️", "done": "✅", "review": "🔍",
            "cancelled": "🚫", "new": "🆕",
        }.get(new_status, "🔄")

        message = (
            f"{status_emoji} <b>{changed_by_name}</b> vazifani yangiladi\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"📊 Yangi holat: {status_names.get(new_status, new_status)}\n\n"
            f"Batafsil: /task_{task.id}"
        )

        if recipient_ids is None:
            recipient_ids = {task.creator_id}

        for user_id in recipient_ids:
            await NotificationService.send_notification(
                bot, session, user_id,
                NotificationType.TASK_STATUS_CHANGED,
                message, task.id,
            )
    
    @staticmethod
    async def notify_overdue_morning_reminder(
        bot: Bot,
        session: AsyncSession,
        user_id: int,
        tasks: list,
    ) -> None:
        """
        Har kuni soat 08:00 da — kechikkan vazifalar eslatmasi.
        Har foydalanuvchiga barcha kechikkan vazifalarini bir xabar bilan yuboradi.
        """
        if not tasks:
            return

        lines = []
        for i, t in enumerate(tasks[:10], 1):
            dl = t.deadline.astimezone(_TZ).strftime('%d.%m %H:%M') if t.deadline else '—'
            p_emoji = {
                "low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"
            }.get(
                t.priority.value if hasattr(t.priority, 'value') else str(t.priority), "⚪"
            )
            lines.append(f"{i}. {p_emoji} <b>{t.title}</b>\n   📅 Deadline: {dl}")

        task_block = "\n\n".join(lines)
        extra = ""
        if len(tasks) > 10:
            extra = f"\n\n... va yana <b>{len(tasks) - 10}</b> ta kechikkan vazifa"

        message = (
            f"🌅 <b>Xayrli tong!</b>\n\n"
            f"❗ Sizda <b>{len(tasks)} ta kechikkan</b> vazifa bor:\n\n"
            f"{task_block}{extra}\n\n"
            f"Iltimos, bugun ularni ko'rib chiqing 💪"
        )

        await NotificationService.send_notification(
            bot, session, user_id,
            NotificationType.TASK_OVERDUE,
            message, None,
        )

    # ── Group chat notifications ──────────────────────────────────────────

    @staticmethod
    async def notify_group_task_created(
        bot: Bot,
        group_telegram_id: int,
        task,  # Task object
    ) -> None:
        """Guruh chatiga yangi vazifa yaratilgani haqida xabar"""
        priority_emoji = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"
        }.get(
            task.priority.value if hasattr(task.priority, 'value') else str(task.priority), "⚪"
        )
        deadline_text = ""
        if task.deadline:
            tz = ZoneInfo("Asia/Tashkent")
            deadline_text = f"\n⏰ <b>Deadline:</b> {task.deadline.astimezone(tz).strftime('%d.%m.%Y %H:%M')}"

        def _mention(u):
            return f"@{u.username}" if getattr(u, "username", None) else u.full_name

        resp_names = []   # masul (responsible)
        obs_names = []    # kuzatuvchilar (observer)
        if hasattr(task, 'assignments') and task.assignments:
            for a in task.assignments:
                if hasattr(a, 'user') and a.user:
                    if a.is_responsible:
                        resp_names.append(_mention(a.user))
                    else:
                        obs_names.append(_mention(a.user))

        assignees_text = ""
        if resp_names:
            assignees_text += "\n⭐ <b>Masul:</b> " + ", ".join(resp_names)
        if obs_names:
            assignees_text += "\n👁 <b>Kuzatuvchilar:</b> " + ", ".join(obs_names)

        creator_name = task.creator.full_name if hasattr(task, 'creator') and task.creator else "Noma'lum"

        message = (
            f"📌 <b>Yangi vazifa yaratildi!</b>\n\n"
            f"📝 <b>{task.title}</b>\n"
            f"{priority_emoji} Muhimlik: {task.priority.value if hasattr(task.priority, 'value') else task.priority}"
            f"{deadline_text}"
            f"{assignees_text}\n"
            f"👤 Yaratdi: {creator_name}"
        )
        # Batafsil ko'rish / status / izoh / tarix tugmasi
        _kb = None
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
            from config import settings as _cfg
            rows = [[InlineKeyboardButton(text="📋 Batafsil ko'rish", callback_data=f"view_task:{task.id}")]]
            if getattr(_cfg, "WEBAPP_URL", None):
                rows.append([InlineKeyboardButton(
                    text="📱 Mini app da ochish", web_app=WebAppInfo(url=_cfg.WEBAPP_URL),
                )])
            _kb = InlineKeyboardMarkup(inline_keyboard=rows)
        except Exception:
            _kb = None
        try:
            await bot.send_message(
                chat_id=group_telegram_id,
                text=message,
                parse_mode="HTML",
                reply_markup=_kb,
            )
        except Exception as e:
            logger.warning(f"Guruh xabari yuborib bo'lmadi {group_telegram_id}: {e}")

    @staticmethod
    async def notify_group_status_changed(
        bot: Bot,
        group_telegram_id: int,
        task,
        old_status: str,
        new_status: str,
        changed_by_name: str,
    ) -> None:
        """Guruh chatiga vazifa statusi o'zgargani haqida xabar"""
        status_names = {
            "new": "🆕 Yangi", "in_progress": "⚙️ Jarayonda",
            "review": "🔍 Ko'rib chiqilmoqda", "done": "✅ Bajarildi",
            "overdue": "⏰ Kechikdi", "cancelled": "🚫 Bekor qilindi",
        }
        message = (
            f"🔄 <b>Vazifa statusi o'zgardi</b>\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"{status_names.get(old_status, old_status)} ➡️ {status_names.get(new_status, new_status)}\n"
            f"👤 O'zgartirdi: {changed_by_name}"
        )
        try:
            await bot.send_message(
                chat_id=group_telegram_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Guruh status xabari yuborib bo'lmadi {group_telegram_id}: {e}")

    @staticmethod
    async def notify_group_daily_tasks(
        bot: Bot,
        group_telegram_id: int,
        group_name: str,
        tasks: list,
    ) -> None:
        """Guruhga kunlik vazifalar ro'yxatini yuborish"""
        if not tasks:
            return
        tz = ZoneInfo("Asia/Tashkent")
        priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
        status_emoji = {
            "new": "🆕", "in_progress": "⚙️", "review": "🔍",
            "done": "✅", "overdue": "🔴", "cancelled": "🚫",
        }
        lines = []
        for t in tasks[:15]:
            p = t.priority.value if hasattr(t.priority, 'value') else str(t.priority)
            s = t.status.value if hasattr(t.status, 'value') else str(t.status)
            dl = t.deadline.astimezone(tz).strftime('%d.%m %H:%M') if t.deadline else '—'

            # Masul ijrochilarni bajargan / qolgan deb ajratamiz
            done_names, pending_names = [], []
            if hasattr(t, 'assignments') and t.assignments:
                resp = [a for a in t.assignments if a.is_responsible and getattr(a, 'user', None)]
                if not resp:
                    resp = [a for a in t.assignments if getattr(a, 'user', None)]
                for a in resp:
                    if (a.status or "new") == "done":
                        done_names.append(a.user.full_name)
                    else:
                        pending_names.append(a.user.full_name)

            resp_lines = ""
            if done_names:
                resp_lines += f"\n   ✅ Bajardi: {', '.join(done_names)}"
            if pending_names:
                resp_lines += f"\n   ⏳ Qoldi: {', '.join(pending_names)}"

            lines.append(
                f"{status_emoji.get(s,'📌')} {priority_emoji.get(p,'⚪')} <b>{t.title}</b>\n"
                f"   ⏰ {dl}{resp_lines}"
            )
        extra = f"\n\n...va yana <b>{len(tasks) - 15}</b> ta" if len(tasks) > 15 else ""
        message = (
            f"📋 <b>{group_name} — bugungi vazifalar</b>\n\n"
            + "\n\n".join(lines)
            + extra
        )
        try:
            await bot.send_message(
                chat_id=group_telegram_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Guruh kunlik xabar yuborib bo'lmadi {group_telegram_id}: {e}")

    @staticmethod
    async def notify_new_comment(
        bot: Bot,
        session: AsyncSession,
        task: Task,
        commenter_name: str,
        content: str,
        recipient_ids: Optional[set] = None,
    ) -> None:
        """Yangi izoh haqida xabar"""
        preview = content[:100] + "..." if len(content) > 100 else content

        message = (
            f"💬 <b>Yangi izoh</b>\n\n"
            f"📌 <b>{task.title}</b>\n"
            f"👤 <b>{commenter_name}</b>\n"
            f"📝 {preview}\n\n"
            f"Batafsil: /task_{task.id}"
        )

        if recipient_ids is None:
            recipient_ids = {task.creator_id}
            for assignment in task.assignments:
                recipient_ids.add(assignment.user_id)

        for user_id in recipient_ids:
            await NotificationService.send_notification(
                bot, session, user_id,
                NotificationType.TASK_COMMENT,
                message, task.id,
            )
