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
from database.models import Task, TaskStatus, TaskAssignment, TaskStep
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

    scheduler.start()
    logger.info("Scheduler ishga tushdi")


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
            day_start = _TZ.localize(datetime.combine(today_local, datetime.min.time())).astimezone(pytz.utc)
            day_end   = _TZ.localize(datetime.combine(today_local, datetime.max.time())).astimezone(pytz.utc)

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
    """Kunlik hisobot — guruh adminlariga grafik bilan"""
    try:
        async with get_session() as session:
            from sqlalchemy import select
            from database.models import Group, GroupMember, UserRole, User
            from services.stats_service import StatsService
            from utils.charts import generate_group_report_chart
            from aiogram.types import BufferedInputFile
            import asyncio

            result = await session.execute(
                select(Group).where(Group.is_active == True)
            )
            groups = list(result.scalars().all())

            for group in groups:
                try:
                    admins_result = await session.execute(
                        select(User)
                        .join(GroupMember, GroupMember.user_id == User.id)
                        .where(
                            and_(
                                GroupMember.group_id == group.id,
                                GroupMember.role == UserRole.ADMIN,
                            )
                        )
                    )
                    admins = list(admins_result.scalars().all())

                    member_stats = await StatsService.get_group_member_stats(
                        session, group.id, days=1
                    )
                    weekly_data = await StatsService.get_weekly_dynamics(
                        session, group_id=group.id
                    )
                    completion_report = await StatsService.get_completion_report(
                        session, group_id=group.id, days=1
                    )

                    if (
                        completion_report["total_created"] == 0
                        and completion_report["total_completed"] == 0
                    ):
                        continue

                    chart_bytes = generate_group_report_chart(
                        member_stats, weekly_data, completion_report
                    )

                    caption = (
                        f"📊 <b>Kunlik hisobot</b>\n"
                        f"👥 {group.name}\n\n"
                        f"📌 Yaratildi: {completion_report['total_created']}\n"
                        f"✅ Bajarildi: {completion_report['total_completed']}\n"
                        f"⏰ Kechikdi: {completion_report['total_overdue']}\n"
                        f"📈 Bajarilish: {completion_report['completion_rate']}%"
                    )

                    for admin in admins:
                        try:
                            chart_file = BufferedInputFile(
                                chart_bytes, filename="daily_report.png"
                            )
                            await bot.send_photo(
                                chat_id=admin.telegram_id,
                                photo=chart_file,
                                caption=caption,
                                parse_mode="HTML",
                            )
                            await asyncio.sleep(0.05)
                        except Exception as e:
                            logger.warning(
                                f"Kunlik hisobot yuborib bo'lmadi "
                                f"{admin.telegram_id}: {e}"
                            )
                except Exception as e:
                    logger.warning(f"Guruh {group.id} hisoboti xatosi: {e}")

            logger.info(f"Kunlik hisobot: {len(groups)} guruh")
    except Exception as e:
        logger.exception(f"daily_report xatosi: {e}")
