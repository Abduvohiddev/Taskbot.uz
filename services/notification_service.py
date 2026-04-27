"""
Notification service - bildirishnomalar yuborish
"""
import logging
from datetime import datetime
from typing import List, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Notification, NotificationType, User, Task

logger = logging.getLogger(__name__)


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
        
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="HTML",
            )
            return True
        except TelegramForbiddenError:
            logger.warning(f"Foydalanuvchi {user.telegram_id} botni blokladi")
            user.is_banned = True
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
    ) -> None:
        """Vazifa biriktirilgani haqida xabar"""
        deadline_text = ""
        if task.deadline:
            deadline_text = f"\n⏰ <b>Deadline:</b> {task.deadline.strftime('%d.%m.%Y %H:%M')}"
        
        priority_emoji = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"
        }.get(task.priority.value, "⚪")
        
        message = (
            f"📌 <b>Sizga yangi vazifa biriktirildi!</b>\n\n"
            f"📝 <b>Nomi:</b> {task.title}\n"
            f"{priority_emoji} <b>Muhimlik:</b> {task.priority.value}"
            f"{deadline_text}\n\n"
            f"Tafsilotlar uchun /task_{task.id}"
        )
        
        for user_id in assignee_ids:
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
        now = datetime.utcnow()
        # Timezone-aware bo'lsa, UTC ga o'tkazish
        if hasattr(deadline, 'tzinfo') and deadline.tzinfo is not None:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("UTC"))
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
            f"⏰ Deadline: {task.deadline.strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>{urgency}</b>\n\n"
            f"Tezroq harakat qiling! /task_{task.id}"
        )

        recipients = {task.creator_id}
        for a in task.assignments:
            recipients.add(a.user_id)

        for user_id in recipients:
            await NotificationService.send_notification(
                bot, session, user_id, notif_type, message, task.id,
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
            f"⏰ Deadline: {step.deadline.strftime('%d.%m.%Y %H:%M')}\n"
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
            f"⏰ Deadline edi: {task.deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Darhol harakat qiling: /task_{task.id}"
        )
        
        recipients = set()
        recipients.add(task.creator_id)
        for assignment in task.assignments:
            recipients.add(assignment.user_id)
        
        for user_id in recipients:
            await NotificationService.send_notification(
                bot, session, user_id,
                NotificationType.TASK_OVERDUE,
                message, task.id,
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
            dl = t.deadline.strftime('%d.%m %H:%M') if t.deadline else '—'
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
