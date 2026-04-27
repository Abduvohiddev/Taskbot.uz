"""
Stats handler - premium 4-chart media group dashboard + team leaderboard
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InputMediaPhoto,
)
from sqlalchemy import select

from database.db import get_session
from database.models import User, UserRole, Company, CompanyMember, Task, TaskAssignment, TaskStatus
from keyboards.inline import (
    back_to_menu_keyboard, stats_workspace_keyboard, leaderboard_keyboard
)
from services.task_service import TaskService
from services.group_service import GroupService
from services.stats_service import StatsService
from utils.charts import (
    generate_status_donut_chart,
    generate_weekly_chart,
    generate_priority_chart,
    generate_summary_card,
    generate_leaderboard_chart,
    generate_team_comparison_chart,
    generate_overdue_chart,
    generate_group_report_chart,
)

router = Router()
logger = logging.getLogger(__name__)


# ── Entry point ────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
@router.message(F.text == "📊 Statistika")
@router.callback_query(F.data == "menu:stats")
async def cmd_stats(event, user: User) -> None:
    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
        is_group = False
    else:
        message = event
        is_group = message.chat.type in ("group", "supergroup")

    if is_group:
        await _send_group_stats(message, user)
        return

    # Private: check companies
    async with get_session() as session:
        res = await session.execute(
            select(Company)
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user.id)
            .order_by(Company.name)
        )
        companies = [{"id": c.id, "name": c.name} for c in res.scalars().all()]

    if not companies:
        # Only personal
        await _send_personal_dashboard(message, user)
        return

    # Show workspace selection
    text = (
        "📊 <b>Statistika</b>\n\n"
        "Qaysi workspace statistikasini ko'rmoqchisiz?"
    )
    kb = stats_workspace_keyboard(companies)
    if hasattr(message, 'photo') and message.photo:
        await message.delete()
        await message.answer(text, reply_markup=kb)
    else:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)


# ── Workspace callbacks ────────────────────────────────────────────────────────

@router.callback_query(F.data == "stats:personal")
async def cb_stats_personal(callback: CallbackQuery, user: User) -> None:
    await callback.answer("⏳ Tayyorlanmoqda...")
    await _send_personal_dashboard(callback.message, user)


@router.callback_query(F.data.startswith("stats:co:"))
async def cb_stats_company(callback: CallbackQuery, user: User) -> None:
    company_id = int(callback.data.split(":")[2])
    await callback.answer("⏳ Tayyorlanmoqda...")
    await _send_team_dashboard(callback.message, user, company_id)


@router.callback_query(F.data.startswith("stats:member:"))
async def cb_stats_member(callback: CallbackQuery, user: User) -> None:
    parts = callback.data.split(":")
    target_user_id = int(parts[2])
    company_id     = int(parts[3])
    await callback.answer("⏳ Tayyorlanmoqda...")
    await _send_member_dashboard(callback.message, user, target_user_id, company_id)


# ── Personal 4-chart dashboard ─────────────────────────────────────────────────

async def _send_personal_dashboard(message: Message, user: User,
                                    company_id: int = None,
                                    rank_info: dict = None) -> None:
    loading = await message.answer("⏳ Dashboard tayyorlanmoqda...")

    async with get_session() as session:
        stats    = await StatsService.get_user_stats(session, user.id, days=30)
        weekly   = await StatsService.get_weekly_dynamics(session, user_id=user.id)
        priority = await StatsService.get_user_priority_stats(
            session, user.id, company_id=company_id
        )

    if stats["total"] == 0:
        await loading.edit_text(
            "📊 <b>Statistika</b>\n\nSizda hali vazifalar yo'q.\n\n"
            "<i>Yangi vazifa: /newtask</i>",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    # Generate 4 charts
    img1 = generate_status_donut_chart(stats, "Vazifalar holati")
    img2 = generate_weekly_chart(weekly, "So'nggi 7 kun")
    img3 = generate_priority_chart(priority, "Muhimlik taqsimoti")
    img4 = generate_summary_card(stats, user.full_name, rank_info=rank_info)

    caption = (
        f"📊 <b>{user.full_name}</b> — shaxsiy dashboard\n"
        f"<i>Oxirgi 30 kun</i>\n\n"
        f"📌 Jami: <b>{stats['total']}</b>  "
        f"✅ Bajarildi: <b>{stats['done']}</b>  "
        f"⏰ Kechikdi: <b>{stats['overdue']}</b>\n"
        f"📈 Bajarilish: <b>{stats['completion_rate']}%</b>"
    )

    media = [
        InputMediaPhoto(media=BufferedInputFile(img1, "status.png"),    caption=caption, parse_mode="HTML"),
        InputMediaPhoto(media=BufferedInputFile(img2, "weekly.png")),
        InputMediaPhoto(media=BufferedInputFile(img3, "priority.png")),
        InputMediaPhoto(media=BufferedInputFile(img4, "card.png")),
    ]

    await loading.delete()
    await message.answer_media_group(media=media)
    await message.answer("⬆️ Dashboard", reply_markup=back_to_menu_keyboard())


# ── Team dashboard (4 charts + leaderboard keyboard) ──────────────────────────

async def _send_team_dashboard(message: Message, user: User, company_id: int) -> None:
    loading = await message.answer("⏳ Jamoa dashboardi tayyorlanmoqda...")

    async with get_session() as session:
        # Company info
        co_res  = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = co_res.scalar_one_or_none()
        co_name = company.name if company else "Jamoa"

        # Team overall stats
        from sqlalchemy import func
        stat_res = await session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.company_id == company_id)
            .group_by(Task.status)
        )
        sc = {row[0].value: row[1] for row in stat_res.all()}
        total = sum(sc.values())
        done  = sc.get("done", 0)
        team_stats = {
            "done": done,
            "in_progress": sc.get("in_progress", 0),
            "review": sc.get("review", 0),
            "new": sc.get("new", 0),
            "overdue": sc.get("overdue", 0),
            "total": total,
            "completion_rate": round(done / total * 100) if total else 0,
        }

        # Weekly dynamics (team)
        weekly = await StatsService.get_weekly_dynamics(session)

        # Member stats with rating
        member_stats = await StatsService.get_company_member_stats(session, company_id)

    if not member_stats and total == 0:
        await loading.edit_text(
            f"📊 <b>{co_name}</b>\n\nVazifalar yo'q.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    # 4 charts
    img1 = generate_status_donut_chart(team_stats, f"{co_name} — holat")
    img2 = generate_leaderboard_chart(member_stats)
    img3 = generate_weekly_chart(weekly, "Haftalik dinamika")
    img4 = generate_team_comparison_chart(member_stats)

    caption = (
        f"🏢 <b>{co_name}</b> — jamoa dashboardi\n\n"
        f"👥 A'zolar: <b>{len(member_stats)}</b>  "
        f"📌 Jami: <b>{total}</b>\n"
        f"✅ Bajarildi: <b>{done}</b>  "
        f"⏰ Kechikdi: <b>{team_stats['overdue']}</b>\n"
        f"📈 Bajarilish: <b>{team_stats['completion_rate']}%</b>"
    )

    media = [
        InputMediaPhoto(media=BufferedInputFile(img1, "team_status.png"),   caption=caption, parse_mode="HTML"),
        InputMediaPhoto(media=BufferedInputFile(img2, "leaderboard.png")),
        InputMediaPhoto(media=BufferedInputFile(img3, "weekly.png")),
        InputMediaPhoto(media=BufferedInputFile(img4, "comparison.png")),
    ]

    await loading.delete()
    await message.answer_media_group(media=media)

    # Leaderboard keyboard for member drilldown
    lb_text = (
        f"🏆 <b>{co_name} reytingi</b>\n\n"
        f"A'zo ustiga bosing — uning to'liq dashboardini ko'ring:\n\n"
        + "\n".join(
            f"{'🥇🥈🥉'[i] if i < 3 else '👤'} "
            f"<b>{m['user_name']}</b> — ⭐{m['score']}  "
            f"✅{m['done']}  ⏰{m['overdue']}"
            for i, m in enumerate(member_stats[:8])
        )
    )
    await message.answer(
        lb_text,
        reply_markup=leaderboard_keyboard(member_stats, company_id),
    )


# ── Member drilldown dashboard ─────────────────────────────────────────────────

async def _send_member_dashboard(message: Message, viewer: User,
                                  target_user_id: int, company_id: int) -> None:
    loading = await message.answer("⏳ Tayyorlanmoqda...")

    async with get_session() as session:
        user_res = await session.execute(
            select(User).where(User.id == target_user_id)
        )
        target = user_res.scalar_one_or_none()
        if not target:
            await loading.edit_text("❗ Foydalanuvchi topilmadi.")
            return

        stats    = await StatsService.get_user_stats(session, target_user_id, days=30)
        weekly   = await StatsService.get_weekly_dynamics(session, user_id=target_user_id)
        priority = await StatsService.get_user_priority_stats(
            session, target_user_id, company_id=company_id
        )
        member_stats = await StatsService.get_company_member_stats(session, company_id)

    rank_info = None
    for m in member_stats:
        if m["user_id"] == target_user_id:
            rank_info = {"rank": m["rank"], "total_members": len(member_stats)}
            break

    img1 = generate_status_donut_chart(stats, "Vazifalar holati")
    img2 = generate_weekly_chart(weekly, "So'nggi 7 kun")
    img3 = generate_priority_chart(priority, "Muhimlik taqsimoti")
    img4 = generate_summary_card(stats, target.full_name, rank_info=rank_info)

    score = max(0, stats['done'] * 10 - stats['overdue'] * 8 + stats['in_progress'] * 2)
    rank_txt = f"#{rank_info['rank']}/{rank_info['total_members']}" if rank_info else ""

    caption = (
        f"👤 <b>{target.full_name}</b>  {rank_txt}\n"
        f"⭐ Reyting: <b>{score}</b>\n\n"
        f"📌 Jami: <b>{stats['total']}</b>  "
        f"✅ Bajarildi: <b>{stats['done']}</b>  "
        f"⏰ Kechikdi: <b>{stats['overdue']}</b>\n"
        f"📈 Bajarilish: <b>{stats['completion_rate']}%</b>"
    )

    media = [
        InputMediaPhoto(media=BufferedInputFile(img1, "status.png"),   caption=caption, parse_mode="HTML"),
        InputMediaPhoto(media=BufferedInputFile(img2, "weekly.png")),
        InputMediaPhoto(media=BufferedInputFile(img3, "priority.png")),
        InputMediaPhoto(media=BufferedInputFile(img4, "card.png")),
    ]

    await loading.delete()
    await message.answer_media_group(media=media)

    # Back to leaderboard
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Reyting", callback_data=f"stats:co:{company_id}"),
        InlineKeyboardButton(text="🏠 Menyu",  callback_data="menu:main"),
    ]])
    await message.answer(f"⬆️ <b>{target.full_name}</b> dashboardi", reply_markup=back_kb)


# ── Group stats (unchanged) ────────────────────────────────────────────────────

async def _send_group_stats(message: Message, user: User) -> None:
    loading = await message.answer("⏳ Guruh statistikasi tayyorlanmoqda...")

    async with get_session() as session:
        group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
        if not group:
            await loading.edit_text("❗ Bu guruh ro'yxatdan o'tmagan. /start yuboring.")
            return

        role = await TaskService.get_user_role_in_group(session, user.id, group.id)
        if not role:
            await loading.edit_text("🚫 Siz bu guruh a'zosi emassiz.")
            return

        group_stats  = await GroupService.get_group_stats(session, group.id)
        member_stats = await StatsService.get_group_member_stats(session, group.id, days=30)

    if group_stats["total_tasks"] == 0:
        await loading.edit_text(f"📊 <b>{group.name}</b>\n\nVazifalar yo'q.")
        return

    sc = group_stats["status_counts"]
    total = group_stats["total_tasks"]
    team_stats = {
        "done": sc.get("done", 0), "in_progress": sc.get("in_progress", 0),
        "review": sc.get("review", 0), "new": sc.get("new", 0),
        "overdue": group_stats.get("overdue_count", 0),
        "total": total,
        "completion_rate": group_stats["completion_rate"],
    }

    img1 = generate_status_donut_chart(team_stats, f"{group.name}")
    img2 = generate_leaderboard_chart(member_stats)

    async with get_session() as session:
        weekly = await StatsService.get_weekly_dynamics(session, group_id=group.id)
    img3 = generate_weekly_chart(weekly, "Haftalik dinamika")
    img4 = generate_team_comparison_chart(member_stats)

    caption = (
        f"📊 <b>{group.name}</b>\n\n"
        f"👥 A'zolar: <b>{group_stats['members_count']}</b>  "
        f"📌 Jami: <b>{total}</b>\n"
        f"✅ Bajarilgan: <b>{sc.get('done', 0)}</b>  "
        f"⏰ Kechikkan: <b>{group_stats['overdue_count']}</b>\n"
        f"📈 Bajarilish: <b>{group_stats['completion_rate']}%</b>"
    )

    media = [
        InputMediaPhoto(media=BufferedInputFile(img1, "status.png"), caption=caption, parse_mode="HTML"),
        InputMediaPhoto(media=BufferedInputFile(img2, "leaderboard.png")),
        InputMediaPhoto(media=BufferedInputFile(img3, "weekly.png")),
        InputMediaPhoto(media=BufferedInputFile(img4, "comparison.png")),
    ]
    await loading.delete()
    await message.answer_media_group(media=media)


@router.message(Command("report"))
async def cmd_report(message: Message, user: User) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("ℹ️ /report faqat guruh chatlarida ishlaydi.")
        return
    await _send_group_stats(message, user)


@router.message(Command("weekly"))
async def cmd_weekly(message: Message, user: User) -> None:
    loading = await message.answer("⏳ Chart tayyorlanmoqda...")

    group_id = None
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if group:
                group_id = group.id

    async with get_session() as session:
        weekly = await StatsService.get_weekly_dynamics(
            session,
            group_id=group_id,
            user_id=user.id if not group_id else None,
        )

    chart_bytes = generate_weekly_chart(weekly)
    chart_file  = BufferedInputFile(chart_bytes, filename="weekly.png")

    await loading.delete()
    await message.answer_photo(
        photo=chart_file,
        caption="📈 <b>Haftalik vazifalar dinamikasi</b>",
    )
