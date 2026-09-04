"""
Scheduler - avtomatik bildirishnomalar va vazifalar
Eslatma jadvali:
  ☀️  Soat 08:00  — bugun deadline bo'lgan vazifalar (warned_24h flag)
  ⚠️  3 soat oldin — warned_4h flag (eski nom saqlanadi)
  🕑  2 soat oldin — warned_2h flag
  🚨  1 soat oldin — warned_1h flag
  🔴  Aynan vaqtida — warned_exact flag
  Workflow qadam deadlinelari ham xuddi shunday eslatiladi.
"""
import logging
from datetime import datetime, timedelta, date

from zoneinfo import ZoneInfo
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, and_, func, cast, Date
from sqlalchemy.orm import selectinload

from config import settings
from database.db import get_session
from database.models import (
    Task, TaskStatus, TaskAssignment, TaskStep, Reminder, User,
    HRDocument, HRAssignment,
)
from services.notification_service import NotificationService
from services.task_service import TaskService

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler = None

_TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
_UTC = ZoneInfo("UTC")


def _now_utc() -> datetime:
    return datetime.now(_UTC)


def setup_scheduler(bot: Bot) -> None:
    """Scheduler ni ishga tushirish"""
    global scheduler

    scheduler = AsyncIOScheduler(timezone=settings.DEFAULT_TIMEZONE)

    # ── Vazifa deadline eslatmalari ─────────────────────────────────────────

    # ☀️  Har kuni soat 08:00 — bugun deadline bo'lgan vazifalar
    scheduler.add_job(
        check_deadlines_morning,
        trigger=CronTrigger(hour=8, minute=0, timezone=settings.DEFAULT_TIMEZONE),
        args=[bot],
        id="check_deadlines_morning",
        replace_existing=True,
        max_instances=1,
    )

    # ⚠️  3 soat oldin — har 10 daqiqada
    scheduler.add_job(
        check_deadlines_3h,
        trigger=IntervalTrigger(minutes=10),
        args=[bot],
        id="check_deadlines_3h",
        replace_existing=True,
        max_instances=1,
    )

    # 🕑  2 soat oldin — har 10 daqiqada
    scheduler.add_job(
        check_deadlines_2h,
        trigger=IntervalTrigger(minutes=10),
        args=[bot],
        id="check_deadlines_2h",
        replace_existing=True,
        max_instances=1,
    )

    # 🚨  1 soat oldin — har 5 daqiqada
    scheduler.add_job(
        check_deadlines_1h,
        trigger=IntervalTrigger(minutes=5),
        args=[bot],
        id="check_deadlines_1h",
        replace_existing=True,
        max_instances=1,
    )

    # 🔴  Aynan vaqtida — har 3 daqiqada
    scheduler.add_job(
        check_deadlines_exact,
        trigger=IntervalTrigger(minutes=3),
        args=[bot],
        id="check_deadlines_exact",
        replace_existing=True,
        max_instances=1,
    )

    # ── Workflow qadam deadline eslatmalari ─────────────────────────────────

    # ☀️  Qadam — soat 08:00
    scheduler.add_job(
        check_steps_morning,
        trigger=CronTrigger(hour=8, minute=0, timezone=settings.DEFAULT_TIMEZONE),
        args=[bot],
        id="check_steps_morning",
        replace_existing=True,
        max_instances=1,
    )

    # ⚠️  Qadam — 3 soat oldin
    scheduler.add_job(
        check_steps_3h,
        trigger=IntervalTrigger(minutes=10),
        args=[bot],
        id="check_steps_3h",
        replace_existing=True,
        max_instances=1,
    )

    # 🕑  Qadam — 2 soat oldin
    scheduler.add_job(
        check_steps_2h,
        trigger=IntervalTrigger(minutes=10),
        args=[bot],
        id="check_steps_2h",
        replace_existing=True,
        max_instances=1,
    )

    # 🚨  Qadam — 1 soat oldin
    scheduler.add_job(
        check_steps_1h,
        trigger=IntervalTrigger(minutes=5),
        args=[bot],
        id="check_steps_1h",
        replace_existing=True,
        max_instances=1,
    )

    # 🔴  Qadam — aynan vaqtida
    scheduler.add_job(
        check_steps_exact,
        trigger=IntervalTrigger(minutes=3),
        args=[bot],
        id="check_steps_exact",
        replace_existing=True,
        max_instances=1,
    )

    # ── Kunlik guruh digest ─────────────────────────────────────────────────

    # 📋 Har kuni soat 09:00 — guruh chatlariga vazifalar ro'yxati
    scheduler.add_job(
        daily_group_digest,
        trigger=CronTrigger(hour=9, minute=0, timezone=settings.DEFAULT_TIMEZONE),
        args=[bot],
        id="daily_group_digest",
        replace_existing=True,
        max_instances=1,
    )

    # ── Kechikkan vazifalar ─────────────────────────────────────────────────

    # Kechikkan vazifalarni OVERDUE deb belgilash — har soatda
    scheduler.add_job(
        check_overdue_tasks,
        trigger=IntervalTrigger(hours=1),
        args=[bot],
        id="check_overdue_tasks",
        replace_existing=True,
        max_instances=1,
    )

    # ── Kunlik hisobot ──────────────────────────────────────────────────────

    scheduler.add_job(
        daily_report,
        trigger=CronTrigger(
            hour=settings.DAILY_REPORT_HOUR, minute=0,
            timezone=settings.DEFAULT_TIMEZONE,
        ),
        args=[bot],
        id="daily_report",
        replace_existing=True,
        max_instances=1,
    )

    # ── 🎯 Kunlik fokus — har kuni 10:00 da top 3 muhim vazifa ──
    scheduler.add_job(
        daily_focus,
        trigger=CronTrigger(hour=10, minute=0, timezone=settings.DEFAULT_TIMEZONE),
        args=[bot],
        id="daily_focus",
        replace_existing=True,
        max_instances=1,
    )

    # ── 📊 Haftalik dayjest — har Dushanba 9:00 da ──
    # day_of_week: 0=mon (apscheduler standart)
    scheduler.add_job(
        weekly_digest,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=settings.DEFAULT_TIMEZONE),
        args=[bot],
        id="weekly_digest",
        replace_existing=True,
        max_instances=1,
    )

    # ── ⏰ AI eslatmalari — har daqiqada tekshiriladi ──
    scheduler.add_job(
        send_due_reminders,
        trigger=IntervalTrigger(minutes=1),
        args=[bot],
        id="ai_reminders",
        replace_existing=True,
        max_instances=1,
    )

    # ── 📄 HR hujjat kunlik eslatmalari — har 20 daqiqada tekshiriladi ──
    scheduler.add_job(
        hr_daily_reminders,
        trigger=IntervalTrigger(minutes=20),
        args=[bot],
        id="hr_daily_reminders",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Scheduler ishga tushdi")


_MOTIVATION = [
    "💪 Sen bu ishni eplaysan, ishonaman!",
    "🚀 Hozir boshlasang — keyin yengil bo'ladi!",
    "🔥 Bir qadam tashla, qolgani o'zi keladi!",
    "⭐ Sen kuchli odamsan, bu vazifa senga bo'ysunadi!",
    "🌟 Kichik harakat — katta natija. Boshladikmi?",
    "👏 O'zingga ishon — sen ulgurasan!",
    "🎯 Diqqatni jamla va zarba ber!",
]


async def send_due_reminders(bot: Bot) -> None:
    """AI maslahatchi qo'ygan eslatmalarni vaqti kelganda yuboradi (motivatsiya bilan)."""
    import random
    now = _now_utc()
    async with get_session() as session:
        res = await session.execute(
            select(Reminder)
            .where(Reminder.is_sent.is_(False), Reminder.remind_at <= now)
            .options(selectinload(Reminder.user), selectinload(Reminder.task))
            .limit(50)
        )
        reminders = list(res.scalars().all())
        if not reminders:
            return

        for rem in reminders:
            user = rem.user
            if not user or not getattr(user, "telegram_id", None):
                rem.is_sent = True
                rem.sent_at = now
                continue

            motiv = random.choice(_MOTIVATION)
            task_line = ""
            if rem.task is not None:
                st = rem.task.status.value if hasattr(rem.task.status, "value") else str(rem.task.status)
                task_line = f"\n📋 Vazifa: <b>{rem.task.title}</b>"
                if rem.task.deadline:
                    dl_local = rem.task.deadline.astimezone(_TZ).strftime("%d.%m %H:%M")
                    task_line += f"\n⏰ Deadline: {dl_local}"

            text = (
                f"🔔 <b>Eslatma!</b>\n\n"
                f"«{rem.text}»"
                f"{task_line}\n\n"
                f"{motiv}"
            )
            try:
                await bot.send_message(user.telegram_id, text)
            except Exception as e:
                logger.warning(f"Eslatma yuborilmadi (user={user.id}): {e}")
            finally:
                rem.is_sent = True
                rem.sent_at = now

        await session.commit()
        logger.info(f"AI eslatmalari yuborildi: {len(reminders)} ta")


async def hr_daily_reminders(bot: Bot) -> None:
    """HR hujjatlari — kunlik eslatma. Belgilangan vaqtdan keyin, hali javob bermagan
    (pending) xodimlarga har kuni bir marta tasdiqlash/rad etish so'rovini qayta yuboradi."""
    now_local = datetime.now(_TZ)
    now_hhmm = now_local.strftime("%H:%M")
    today = now_local.strftime("%Y-%m-%d")

    async with get_session() as session:
        docs_res = await session.execute(
            select(HRDocument).where(
                HRDocument.remind_enabled.is_(True),
                HRDocument.remind_time.isnot(None),
            )
        )
        docs = list(docs_res.scalars().all())
        if not docs:
            return

        try:
            from handlers.hr import hr_doc_keyboard
        except Exception as e:
            logger.warning(f"hr_doc_keyboard import xato: {e}")
            return

        sent_count = 0
        from datetime import date as _date
        today_d = now_local.date()

        for doc in docs:
            # Belgilangan vaqt keldimi? (o'sha vaqtdan keyin, kuniga bir marta)
            if not doc.remind_time or now_hhmm < doc.remind_time:
                continue

            interval = int(getattr(doc, "remind_interval_days", 0) or 0)

            # ── 1) Har N kunda QAYTA OCHISH — javob berganlarni ham pending qilamiz ──
            reopened_ids = set()
            if interval >= 1:
                last_reopen = getattr(doc, "last_reopen_on", None)
                due = True
                if last_reopen:
                    try:
                        y, m, d = map(int, last_reopen.split("-"))
                        due = (today_d - _date(y, m, d)).days >= interval
                    except Exception:
                        due = True
                if due:
                    ans_res = await session.execute(
                        select(HRAssignment).where(
                            HRAssignment.document_id == doc.id,
                            HRAssignment.status.in_(["confirmed", "rejected"]),
                        )
                    )
                    for a in ans_res.scalars().all():
                        a.status = "pending"
                        a.responded_at = None
                        a.comment = None
                        a.last_reminded_on = None   # bugun eslatilsin
                        reopened_ids.add(a.id)
                    doc.last_reopen_on = today

            # ── 2) Javob bermaganlarga (pending) har kuni eslatma ──
            asg_res = await session.execute(
                select(HRAssignment, User)
                .join(User, HRAssignment.user_id == User.id)
                .where(
                    HRAssignment.document_id == doc.id,
                    HRAssignment.status == "pending",
                )
            )
            for asgn, user in asg_res.all():
                if (asgn.last_reminded_on or "") == today:
                    continue  # bugun allaqachon eslatilgan
                if not getattr(user, "telegram_id", None):
                    asgn.last_reminded_on = today
                    continue

                if asgn.id in reopened_ids:
                    header = (
                        f"🔄 <b>Qayta tasdiqlash</b>\n\n"
                        f"📄 <b>{doc.name}</b>\n\n"
                        f"Iltimos, ushbu hujjatni qaytadan tasdiqlang yoki rad eting ⬇️"
                    )
                else:
                    header = (
                        f"⏰ <b>Eslatma!</b>\n\n"
                        f"📄 <b>{doc.name}</b> hujjatini hali ko'rib chiqmadingiz.\n\n"
                        f"HR bo'limi sizdan tasdiqlash yoki rad etishingizni kutmoqda ⬇️"
                    )
                try:
                    await bot.send_message(
                        user.telegram_id, header,
                        reply_markup=hr_doc_keyboard(asgn.id),
                    )
                    asgn.last_reminded_on = today
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"HR eslatma yuborilmadi (user={user.id}): {e}")
                    asgn.last_reminded_on = today  # xato bo'lsa ham bugun qayta urinmaymiz

        await session.commit()
        if sent_count:
            logger.info(f"HR kunlik eslatmalar yuborildi: {sent_count} ta")


async def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler to'xtadi")


# ═══════════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYA — window ichidagi vazifalarni topish
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_tasks_in_window(session, window_start, window_end, flag_col):
    """
    deadline window_start..window_end oralig'ida, flag_col=False bo'lgan,
    bajarilmagan vazifalarni qaytaradi.
    """
    result = await session.execute(
        select(Task).where(
            and_(
                Task.deadline.between(window_start, window_end),
                Task.status.notin_([
                    TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.OVERDUE
                ]),
                flag_col == False,  # noqa: E712
            )
        ).options(
            selectinload(Task.assignments).selectinload(TaskAssignment.user),
        )
    )
    return list(result.scalars().all())


async def _fetch_steps_in_window(session, window_start, window_end, flag_col):
    """Workflow qadam — deadline window ichida, flag=False, status active/pending"""
    result = await session.execute(
        select(TaskStep).where(
            and_(
                TaskStep.deadline.isnot(None),
                TaskStep.deadline.between(window_start, window_end),
                TaskStep.status.in_(["active", "pending"]),
                flag_col == False,  # noqa: E712
            )
        )
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════════════
#  ☀️  ERTALABKI 08:00 ESLATMASI — bugun deadline bo'lgan vazifalar
# ═══════════════════════════════════════════════════════════════════════════

async def check_deadlines_morning(bot: Bot) -> None:
    """Soat 08:00 — bugun deadline bo'lgan barcha vazifalar"""
    try:
        async with get_session() as session:
            now = _now_utc()
            # Bugunning oxirigacha (local 23:59:59 ga mos UTC)
            today_local = now.astimezone(_TZ).date()
            day_start = datetime.combine(today_local, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            day_end   = datetime.combine(today_local, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)

            result = await session.execute(
                select(Task).where(
                    and_(
                        Task.deadline.between(day_start, day_end),
                        Task.status.notin_([
                            TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.OVERDUE
                        ]),
                        Task.warned_24h == False,  # noqa: E712
                    )
                ).options(
                    selectinload(Task.assignments).selectinload(TaskAssignment.user),
                )
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                await NotificationService.notify_deadline_warning(bot, session, task)
                task.warned_24h = True

            if tasks:
                await session.commit()
                logger.info(f"☀️  Ertalabki eslatma: {len(tasks)} ta vazifa")
    except Exception as e:
        logger.exception(f"check_deadlines_morning xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  ⚠️  3 SOAT OLDIN
# ═══════════════════════════════════════════════════════════════════════════

async def check_deadlines_3h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            tasks = await _fetch_tasks_in_window(
                session, now, now + timedelta(hours=3), Task.warned_4h
            )
            for task in tasks:
                await NotificationService.notify_deadline_warning(bot, session, task)
                task.warned_4h = True
            if tasks:
                await session.commit()
                logger.info(f"⚠️  3 soat: {len(tasks)} ta vazifa")
    except Exception as e:
        logger.exception(f"check_deadlines_3h xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  🕑  2 SOAT OLDIN
# ═══════════════════════════════════════════════════════════════════════════

async def check_deadlines_2h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            tasks = await _fetch_tasks_in_window(
                session, now, now + timedelta(hours=2), Task.warned_2h
            )
            for task in tasks:
                await NotificationService.notify_deadline_warning(bot, session, task)
                task.warned_2h = True
            if tasks:
                await session.commit()
                logger.info(f"🕑  2 soat: {len(tasks)} ta vazifa")
    except Exception as e:
        logger.exception(f"check_deadlines_2h xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  🚨  1 SOAT OLDIN
# ═══════════════════════════════════════════════════════════════════════════

async def check_deadlines_1h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            tasks = await _fetch_tasks_in_window(
                session, now, now + timedelta(hours=1), Task.warned_1h
            )
            for task in tasks:
                await NotificationService.notify_deadline_warning(bot, session, task)
                task.warned_1h = True
            if tasks:
                await session.commit()
                logger.info(f"🚨  1 soat: {len(tasks)} ta vazifa")
    except Exception as e:
        logger.exception(f"check_deadlines_1h xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  🔴  AYNAN VAQTIDA (± 3 daqiqa)
# ═══════════════════════════════════════════════════════════════════════════

async def check_deadlines_exact(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            tasks = await _fetch_tasks_in_window(
                session,
                now - timedelta(minutes=3),
                now + timedelta(minutes=3),
                Task.warned_exact,
            )
            for task in tasks:
                await NotificationService.notify_deadline_warning(bot, session, task)
                task.warned_exact = True
            if tasks:
                await session.commit()
                logger.info(f"🔴  Aynan vaqt: {len(tasks)} ta vazifa")
    except Exception as e:
        logger.exception(f"check_deadlines_exact xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  WORKFLOW QADAM ESLATMALARI
# ═══════════════════════════════════════════════════════════════════════════

async def check_steps_morning(bot: Bot) -> None:
    """Soat 08:00 — bugun deadline bo'lgan qadam ijrochilarga"""
    try:
        async with get_session() as session:
            now = _now_utc()
            today_local = now.astimezone(_TZ).date()
            day_start = datetime.combine(today_local, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            day_end   = datetime.combine(today_local, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)

            result = await session.execute(
                select(TaskStep).where(
                    and_(
                        TaskStep.deadline.isnot(None),
                        TaskStep.deadline.between(day_start, day_end),
                        TaskStep.status.in_(["active", "pending"]),
                        TaskStep.step_warned_morning == False,  # noqa: E712
                    )
                )
            )
            steps = list(result.scalars().all())
            for step in steps:
                await NotificationService.notify_step_deadline_warning(bot, session, step, "morning")
                step.step_warned_morning = True
            if steps:
                await session.commit()
                logger.info(f"☀️  Qadam ertalabki: {len(steps)} qadam")
    except Exception as e:
        logger.exception(f"check_steps_morning xatosi: {e}")


async def check_steps_3h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            steps = await _fetch_steps_in_window(
                session, now, now + timedelta(hours=3), TaskStep.step_warned_3h
            )
            for step in steps:
                await NotificationService.notify_step_deadline_warning(bot, session, step, "3h")
                step.step_warned_3h = True
            if steps:
                await session.commit()
                logger.info(f"⚠️  Qadam 3 soat: {len(steps)}")
    except Exception as e:
        logger.exception(f"check_steps_3h xatosi: {e}")


async def check_steps_2h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            steps = await _fetch_steps_in_window(
                session, now, now + timedelta(hours=2), TaskStep.step_warned_2h
            )
            for step in steps:
                await NotificationService.notify_step_deadline_warning(bot, session, step, "2h")
                step.step_warned_2h = True
            if steps:
                await session.commit()
                logger.info(f"🕑  Qadam 2 soat: {len(steps)}")
    except Exception as e:
        logger.exception(f"check_steps_2h xatosi: {e}")


async def check_steps_1h(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            steps = await _fetch_steps_in_window(
                session, now, now + timedelta(hours=1), TaskStep.step_warned_1h
            )
            for step in steps:
                await NotificationService.notify_step_deadline_warning(bot, session, step, "1h")
                step.step_warned_1h = True
            if steps:
                await session.commit()
                logger.info(f"🚨  Qadam 1 soat: {len(steps)}")
    except Exception as e:
        logger.exception(f"check_steps_1h xatosi: {e}")


async def check_steps_exact(bot: Bot) -> None:
    try:
        async with get_session() as session:
            now = _now_utc()
            steps = await _fetch_steps_in_window(
                session,
                now - timedelta(minutes=3),
                now + timedelta(minutes=3),
                TaskStep.step_warned_exact,
            )
            for step in steps:
                await NotificationService.notify_step_deadline_warning(bot, session, step, "exact")
                step.step_warned_exact = True
            if steps:
                await session.commit()
                logger.info(f"🔴  Qadam aynan vaqt: {len(steps)}")
    except Exception as e:
        logger.exception(f"check_steps_exact xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  Kechikkan vazifalarni OVERDUE deb belgilash
# ═══════════════════════════════════════════════════════════════════════════

async def check_overdue_tasks(bot: Bot) -> None:
    """Vaqti o'tgan vazifalarni OVERDUE deb belgilash"""
    try:
        async with get_session() as session:
            now = _now_utc()

            result = await session.execute(
                select(Task).where(
                    and_(
                        Task.deadline < now,
                        Task.status.in_([
                            TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW
                        ]),
                    )
                ).options(
                    selectinload(Task.assignments).selectinload(TaskAssignment.user),
                )
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                task.status = TaskStatus.OVERDUE
                await session.flush()
                try:
                    await NotificationService.notify_task_overdue(bot, session, task)
                except Exception as notify_err:
                    logger.warning(f"Overdue notify xatosi task={task.id}: {notify_err}")

            if tasks:
                await session.commit()
                logger.info(f"Kechikdi: {len(tasks)} vazifa")
    except Exception as e:
        logger.exception(f"check_overdue_tasks xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  Kunlik ERTALABKI eslatma — kechikkan vazifalar (soat 08:00 bilan birga)
# ═══════════════════════════════════════════════════════════════════════════

async def daily_morning_reminder(bot: Bot) -> None:
    """
    Har kuni soat 08:00 — foydalanuvchilarga o'zlarining
    kechikkan (OVERDUE) vazifalarini eslatish.
    (check_deadlines_morning bilan parallel ishlaydi)
    """
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Task).where(
                    Task.status == TaskStatus.OVERDUE,
                ).options(
                    selectinload(Task.assignments).selectinload(TaskAssignment.user),
                )
            )
            overdue_tasks = list(result.scalars().all())

            if not overdue_tasks:
                return

            user_tasks: dict[int, list] = {}
            for task in overdue_tasks:
                uid = task.creator_id
                user_tasks.setdefault(uid, [])
                if task not in user_tasks[uid]:
                    user_tasks[uid].append(task)
                for assignment in task.assignments:
                    if assignment.status in ('done', 'cancelled'):
                        continue
                    uid = assignment.user_id
                    user_tasks.setdefault(uid, [])
                    if task not in user_tasks[uid]:
                        user_tasks[uid].append(task)

            sent = 0
            for user_id, tasks in user_tasks.items():
                try:
                    await NotificationService.notify_overdue_morning_reminder(
                        bot, session, user_id, tasks
                    )
                    sent += 1
                except Exception as e:
                    logger.warning(f"Morning reminder xatosi user={user_id}: {e}")

            logger.info(f"Ertalabki kechikkan eslatma: {sent} foydalanuvchi")
    except Exception as e:
        logger.exception(f"daily_morning_reminder xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  Admin kunlik hisobot
# ═══════════════════════════════════════════════════════════════════════════

async def daily_report(bot: Bot) -> None:
    """
    Kunlik shaxsiy hisobot — har bir foydalanuvchiga o'z jamoalaridagi
    vazifalar statistikasini pie chart bilan yuboradi.
    """
    try:
        import asyncio
        from database.models import User
        from services.stats_service import StatsService
        from utils.charts import generate_personal_daily_chart
        from aiogram.types import BufferedInputFile

        async with get_session() as session:
            users_res = await session.execute(
                select(User).where(
                    User.is_banned == False,
                    User.notifications_enabled == True,
                    User.telegram_id.isnot(None),
                )
            )
            users = list(users_res.scalars().all())

            now_tz   = datetime.now(_TZ)
            date_str = now_tz.strftime("%d.%m.%Y, %H:%M")

            sent = 0
            for user in users:
                try:
                    report_data = await StatsService.get_user_daily_report_data(
                        session, user.id
                    )
                    if not report_data:
                        # Bo'sh — qisqa "🎉" xabari
                        try:
                            from database.models import Task as _T3
                            cr_n = (await session.execute(
                                select(func.count(_T3.id)).where(_T3.creator_id == user.id)
                            )).scalar() or 0
                            if cr_n == 0:
                                continue   # umuman vazifa yaratmagan
                            await bot.send_message(
                                user.telegram_id,
                                f"📊 <b>Kunlik shaxsiy hisobot</b>\n"
                                f"📅 {date_str}\n\n"
                                f"🎉 <b>Sizda hozircha mas'ul vazifa yo'q!</b>\n\n"
                                f"<i>Yaratgan vazifalaringiz: {cr_n}.</i>\n"
                                f"<i>Yangi vazifa olganingizda bu yerda ko'rinasiz.</i>",
                                parse_mode="HTML",
                            )
                            sent += 1
                        except Exception:
                            pass
                        continue

                    total_all = sum(d["total"]       for d in report_data)
                    done_all  = sum(d["done"]        for d in report_data)
                    prog_all  = sum(d["in_progress"] for d in report_data)
                    new_all   = sum(d["new"]         for d in report_data)
                    over_all  = sum(d["overdue"]     for d in report_data)
                    rate_all  = round(done_all / total_all * 100) if total_all else 0

                    chart_bytes = generate_personal_daily_chart(
                        user_name=user.full_name,
                        report_data=report_data,
                        date_str=date_str,
                    )

                    lines = [
                        f"📊 <b>Kunlik shaxsiy hisobotingiz</b>",
                        f"👤 {user.full_name}",
                        f"📅 {date_str}\n",
                        f"📌 Jami vazifalar: <b>{total_all}</b>",
                        f"✅ Bajarildi: <b>{done_all}</b>",
                        f"⚙️ Jarayonda: <b>{prog_all}</b>",
                        f"🆕 Yangi: <b>{new_all}</b>",
                        f"🔴 Kechikdi: <b>{over_all}</b>",
                        f"📈 Bajarilish: <b>{rate_all}%</b>",
                    ]
                    if len(report_data) > 1:
                        lines.append("\n<b>Jamoalar bo'yicha:</b>")
                        for d in report_data:
                            name = d["company_name"]
                            lines.append(
                                f"  📁 <b>{name}</b>: "
                                f"{d['done']}✅ {d['in_progress']}⚙️ "
                                f"{d['new']}🆕 {d['overdue']}🔴 "
                                f"(jami: {d['total']})"
                            )

                    caption = "\n".join(lines)

                    chart_file = BufferedInputFile(
                        chart_bytes, filename="personal_report.png"
                    )
                    await bot.send_photo(
                        chat_id=user.telegram_id,
                        photo=chart_file,
                        caption=caption,
                        parse_mode="HTML",
                    )
                    sent += 1
                    await asyncio.sleep(0.05)

                except Exception as e:
                    logger.warning(
                        f"Shaxsiy hisobot yuborib bo'lmadi user={user.id}: {e}"
                    )

            logger.info(f"Kunlik shaxsiy hisobot: {sent}/{len(users)} foydalanuvchi")
    except Exception as e:
        logger.exception(f"daily_report xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  📋  KUNLIK GURUH DIGEST — soat 09:00 da guruh chatiga vazifalar
# ═══════════════════════════════════════════════════════════════════════════

async def daily_group_digest(bot: Bot) -> None:
    """
    Har kuni soat 09:00 — barcha aktiv guruh chatlariga o'sha guruhning
    aktiv (new/in_progress/review/overdue) vazifalarini yuboradi.
    Mas'ul odamlarga ham shaxsiy xabar yuboradi.
    """
    try:
        from database.models import Group, GroupMember, UserRole, User, Company
        from services.notification_service import NotificationService
        from sqlalchemy import or_
        import asyncio

        async with get_session() as session:
            # Barcha aktiv guruhlarni olamiz
            groups_res = await session.execute(
                select(Group).where(Group.is_active == True, Group.company_id.isnot(None))
            )
            groups = list(groups_res.scalars().all())

            for group in groups:
                try:
                    if not group.telegram_group_id:
                        continue

                    # Guruhning aktiv vazifalarini olamiz
                    tasks_res = await session.execute(
                        select(Task).where(
                            Task.company_id == group.company_id,
                            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                        ).options(
                            selectinload(Task.assignments).selectinload(TaskAssignment.user),
                        ).order_by(Task.deadline.asc().nullslast())
                    )
                    tasks = list(tasks_res.scalars().all())

                    # Zaxira filtr: barcha masul ijrochilar 'done' bo'lsa —
                    # vazifa amalda yakunlangan (task.status qotib qolgan bo'lsa ham
                    # bugungi vazifalarda chiqmasin)
                    def _effectively_done(task):
                        resp = [a for a in (task.assignments or []) if a.is_responsible]
                        if not resp:
                            resp = task.assignments or []
                        return bool(resp) and all((a.status or "new") == "done" for a in resp)

                    tasks = [t for t in tasks if not _effectively_done(t)]

                    if not tasks:
                        continue

                    # Guruh chatiga xabar
                    await NotificationService.notify_group_daily_tasks(
                        bot, group.telegram_group_id, group.name, tasks
                    )

                    # Mas'ul odamlarga shaxsiy xabar (task list) —
                    # o'z qismini bajargan odamga o'sha vazifa chiqmaydi
                    user_tasks: dict[int, list] = {}
                    for task in tasks:
                        for a in (task.assignments or []):
                            if a.is_responsible and (a.status or "new") != "done":
                                user_tasks.setdefault(a.user_id, [])
                                user_tasks[a.user_id].append(task)

                    tz = _TZ
                    p_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
                    s_emoji = {
                        "new": "🆕", "in_progress": "⚙️", "review": "🔍",
                        "overdue": "🔴",
                    }
                    for uid, utasks in user_tasks.items():
                        lines = []
                        for t in utasks[:10]:
                            p = t.priority.value if hasattr(t.priority, 'value') else str(t.priority)
                            s = t.status.value if hasattr(t.status, 'value') else str(t.status)
                            dl = t.deadline.astimezone(tz).strftime('%d.%m %H:%M') if t.deadline else '—'
                            lines.append(
                                f"{s_emoji.get(s,'📌')} {p_emoji.get(p,'⚪')} <b>{t.title}</b> — ⏰ {dl}"
                            )
                        msg = (
                            f"📋 <b>{group.name}</b> guruhidagi sizning vazifalaringiz:\n\n"
                            + "\n".join(lines)
                        )
                        try:
                            usr_res = await session.execute(select(User).where(User.id == uid))
                            usr = usr_res.scalar_one_or_none()
                            if usr and not usr.is_banned and usr.notifications_enabled:
                                await bot.send_message(
                                    chat_id=usr.telegram_id,
                                    text=msg,
                                    parse_mode="HTML",
                                )
                                await asyncio.sleep(0.05)
                        except Exception as e:
                            logger.warning(f"Digest personal xabar xatosi uid={uid}: {e}")

                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning(f"Guruh {group.id} digest xatosi: {e}")

            logger.info(f"Kunlik guruh digest: {len(groups)} guruh")
    except Exception as e:
        logger.exception(f"daily_group_digest xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 🎯 Kunlik fokus — har kuni 10:00 da top 3 muhim vazifa
# ═══════════════════════════════════════════════════════════════════════════

PRIORITY_WEIGHT = {"urgent": 4, "high": 3, "medium": 2, "low": 1}


async def daily_focus(bot: Bot) -> None:
    """Har bir foydalanuvchiga bugungi top 3 muhim vazifani yuborish."""
    try:
        from database.models import User
        async with get_session() as session:
            users_res = await session.execute(
                select(User).where(
                    User.is_banned == False,
                    User.notifications_enabled == True,
                    User.telegram_id.isnot(None),
                )
            )
            users = list(users_res.scalars().all())
            now = _now_utc()
            today_local = now.astimezone(_TZ).date()
            week_later = today_local + timedelta(days=7)
            week_end = datetime.combine(week_later, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)

            sent = 0
            for u in users:
                try:
                    # Faqat MAS'UL bo'lgan, hali bajarilmagan, deadline yaqin yoki kechikkanlar
                    res = await session.execute(
                        select(Task).join(TaskAssignment, TaskAssignment.task_id == Task.id)
                        .where(
                            TaskAssignment.user_id == u.id,
                            TaskAssignment.is_responsible.is_(True),
                            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                        )
                        .distinct()
                    )
                    tasks = list(res.scalars().unique().all())
                    if not tasks:
                        # Bo'sh bo'lsa — qisqa "yaxshi ish" xabari (jim qolmaslik uchun)
                        # Faqat foydalanuvchi creator yoki observer bo'lgan bo'lsa yuboramiz
                        from database.models import Task as _T2
                        creator_n = (await session.execute(
                            select(func.count(_T2.id)).where(_T2.creator_id == u.id)
                        )).scalar() or 0
                        obs_n = (await session.execute(
                            select(func.count(TaskAssignment.id)).where(
                                TaskAssignment.user_id == u.id,
                                TaskAssignment.is_responsible.is_(False),
                            )
                        )).scalar() or 0
                        if creator_n == 0 and obs_n == 0:
                            continue   # umuman vazifa bilan ishlamaydi → skip
                        try:
                            empty_msg = (
                                f"🎉 <b>Bugungi fokus — {today_local.strftime('%d.%m.%Y')}</b>\n\n"
                                f"Sizda hozir <b>mas'ul aktiv vazifa yo'q</b> — tabriklaymiz!\n\n"
                                f"📋 Yaratgan vazifalaringiz: <b>{creator_n}</b>\n"
                                f"👁 Kuzatuvchi sifatida: <b>{obs_n}</b>\n\n"
                                f"<i>Yangi vazifa olganingizda darrov xabar qilaman 💪</i>"
                            )
                            await bot.send_message(u.telegram_id, empty_msg, parse_mode="HTML")
                            sent += 1
                        except Exception:
                            pass
                        continue

                    # Scoring: prioritet * 10 + (deadline urgency)
                    def _score(t):
                        pri = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
                        score = PRIORITY_WEIGHT.get(pri, 2) * 10
                        if t.deadline:
                            hrs = (t.deadline - now).total_seconds() / 3600
                            if hrs < 0:
                                score += 50  # kechikkan — eng yuqori prioritet
                            elif hrs < 24:
                                score += 30
                            elif hrs < 72:
                                score += 15
                            elif hrs < 168:  # 7 kun
                                score += 5
                        return score

                    tasks.sort(key=_score, reverse=True)
                    top3 = tasks[:3]
                    if not top3:
                        continue

                    lines = [
                        f"🎯 <b>Bugungi fokus — {today_local.strftime('%d.%m.%Y')}</b>",
                        f"<i>Eng muhim {len(top3)} ta vazifangiz:</i>",
                        "",
                    ]
                    pri_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
                    for i, t in enumerate(top3, 1):
                        pri_val = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
                        st_val = t.status.value if hasattr(t.status, "value") else str(t.status)
                        emo = pri_emoji.get(pri_val, "•")
                        line = f"{i}. {emo} <b>{t.title[:70]}</b>"
                        if t.deadline:
                            dl_local = t.deadline.astimezone(_TZ)
                            hrs_left = (t.deadline - now).total_seconds() / 3600
                            if hrs_left < 0:
                                line += f"\n   ⏰ <b>Kechikdi</b> ({dl_local.strftime('%d.%m %H:%M')})"
                            elif hrs_left < 24:
                                line += f"\n   ⏰ Bugun {dl_local.strftime('%H:%M')}"
                            else:
                                line += f"\n   ⏰ {dl_local.strftime('%d.%m %H:%M')}"
                        line += f"\n   📋 /task_{t.id}"
                        lines.append(line)
                        lines.append("")

                    msg = "\n".join(lines).rstrip()
                    await bot.send_message(u.telegram_id, msg, parse_mode="HTML")
                    sent += 1
                except Exception as e:
                    logger.warning(f"daily_focus user={u.id} xato: {e}")

            if sent:
                logger.info(f"Kunlik fokus: {sent} foydalanuvchiga yuborildi")
    except Exception as e:
        logger.exception(f"daily_focus xatosi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 📊 Haftalik dayjest — har dushanba 9:00 da
# ═══════════════════════════════════════════════════════════════════════════

async def weekly_digest(bot: Bot) -> None:
    """Har bir foydalanuvchiga o'tgan hafta natijasi + bu hafta rejasi."""
    try:
        from database.models import User
        async with get_session() as session:
            users_res = await session.execute(
                select(User).where(
                    User.is_banned == False,
                    User.notifications_enabled == True,
                    User.telegram_id.isnot(None),
                )
            )
            users = list(users_res.scalars().all())
            now = _now_utc()
            today_local = now.astimezone(_TZ).date()
            # O'tgan hafta: dushanba-yakshanba (oldingi)
            last_mon = today_local - timedelta(days=7)
            last_sun = today_local - timedelta(days=1)
            last_mon_utc = datetime.combine(last_mon, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            last_sun_utc = datetime.combine(last_sun, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)
            # Bu hafta: bugundan keyingi 7 kun
            week_end_local = today_local + timedelta(days=7)
            week_end_utc = datetime.combine(week_end_local, datetime.max.time(), tzinfo=_TZ).astimezone(_UTC)

            sent = 0
            for u in users:
                try:
                    # O'tgan hafta — bajarilganlar
                    done_res = await session.execute(
                        select(func.count(TaskAssignment.id))
                        .join(Task, Task.id == TaskAssignment.task_id)
                        .where(
                            TaskAssignment.user_id == u.id,
                            TaskAssignment.is_responsible.is_(True),
                            TaskAssignment.status == "done",
                            TaskAssignment.completed_at >= last_mon_utc,
                            TaskAssignment.completed_at <= last_sun_utc,
                        )
                    )
                    done_n = done_res.scalar() or 0

                    # O'tgan hafta — kechikib bajarilgan
                    late_res = await session.execute(
                        select(func.count(TaskAssignment.id))
                        .join(Task, Task.id == TaskAssignment.task_id)
                        .where(
                            TaskAssignment.user_id == u.id,
                            TaskAssignment.is_responsible.is_(True),
                            TaskAssignment.status == "done",
                            TaskAssignment.completed_at >= last_mon_utc,
                            TaskAssignment.completed_at <= last_sun_utc,
                            Task.deadline.isnot(None),
                            TaskAssignment.completed_at > Task.deadline,
                        )
                    )
                    late_n = late_res.scalar() or 0
                    on_time = done_n - late_n

                    # Bu hafta — deadline'i shu haftada bo'lgan, hali bajarilmagan
                    upcoming_res = await session.execute(
                        select(Task)
                        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
                        .where(
                            TaskAssignment.user_id == u.id,
                            TaskAssignment.is_responsible.is_(True),
                            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                            Task.deadline.isnot(None),
                            Task.deadline <= week_end_utc,
                        )
                        .order_by(Task.deadline.asc())
                        .limit(10)
                        .distinct()
                    )
                    upcoming = list(upcoming_res.scalars().unique().all())

                    # Aktiv (hali bajarilmagan) jami
                    active_res = await session.execute(
                        select(func.count(TaskAssignment.id.distinct()))
                        .join(Task, Task.id == TaskAssignment.task_id)
                        .where(
                            TaskAssignment.user_id == u.id,
                            TaskAssignment.is_responsible.is_(True),
                            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                        )
                    )
                    active_n = active_res.scalar() or 0

                    if done_n == 0 and len(upcoming) == 0 and active_n == 0:
                        continue   # to'liq bo'sh — yubormaymiz

                    # Xabar matni
                    lines = [
                        f"📊 <b>Haftalik dayjest</b>",
                        f"<i>{last_mon.strftime('%d.%m')} — {last_sun.strftime('%d.%m.%Y')}</i>",
                        "",
                        f"<b>📈 O'tgan hafta natijalari:</b>",
                        f"  ✅ Bajardingiz: <b>{done_n}</b>",
                        f"  ⏰ Vaqtida: <b>{on_time}</b> · Kechikib: <b>{late_n}</b>",
                    ]
                    if done_n > 0:
                        rate = round(on_time / done_n * 100)
                        lines.append(f"  🎯 Intizom darajasi: <b>{rate}%</b>")
                    lines.append("")
                    lines.append(f"<b>🗓 Bu hafta rejasi:</b>")
                    lines.append(f"  📌 Aktiv vazifalar: <b>{active_n}</b>")
                    if upcoming:
                        lines.append(f"  🔜 Yaqin deadline ({len(upcoming)}):")
                        pri_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
                        for t in upcoming[:5]:
                            pri_val = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
                            emo = pri_emoji.get(pri_val, "•")
                            dl_local = t.deadline.astimezone(_TZ)
                            lines.append(f"     {emo} {t.title[:50]} — <i>{dl_local.strftime('%d.%m %H:%M')}</i>")
                        if len(upcoming) > 5:
                            lines.append(f"     ... va yana {len(upcoming) - 5} ta")
                    else:
                        lines.append("  🔜 Yaqin deadline yo'q")

                    lines.append("")
                    lines.append("<i>💪 Yaxshi hafta tilaymiz!</i>")

                    msg = "\n".join(lines)
                    await bot.send_message(u.telegram_id, msg, parse_mode="HTML")
                    sent += 1
                except Exception as e:
                    logger.warning(f"weekly_digest user={u.id} xato: {e}")

            if sent:
                logger.info(f"Haftalik dayjest: {sent} foydalanuvchiga yuborildi")
    except Exception as e:
        logger.exception(f"weekly_digest xatosi: {e}")
