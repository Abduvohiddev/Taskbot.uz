"""
Groups handler - guruh va a'zolar boshqaruvi
"""
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)
from aiogram.filters.chat_member_updated import (
    ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_session
from database.models import User, UserRole, GroupMember, CompanyMember, CompanyRole, Group
from services.company_service import CompanyService
from keyboards.inline import (
    group_admin_keyboard, back_to_menu_keyboard, task_list_keyboard,
)
from services.group_service import GroupService
from services.task_service import TaskService
from services.stats_service import StatsService
from utils.charts import generate_overdue_chart, generate_group_report_chart
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("groups"))
@router.callback_query(F.data == "menu:groups")
async def cmd_groups(event, user: User) -> None:
    """Foydalanuvchi guruhlari ro'yxati"""
    if isinstance(event, CallbackQuery):
        message = event.message
        edit = True
        await event.answer()
    else:
        message = event
        edit = False
    
    async with get_session() as session:
        groups = await GroupService.get_user_groups(session, user.id)
    
    if not groups:
        text = (
            "📂 <b>Guruhlar yo'q</b>\n\n"
            "Meni o'z Telegram guruhingizga qo'shing:\n"
            "1. Guruh sozlamalariga kiring\n"
            "2. 'Administratorlar' ga bosing\n"
            "3. Meni qo'shing\n"
            "4. /start buyrug'ini yuboring"
        )
        if edit:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        else:
            await message.answer(text, reply_markup=back_to_menu_keyboard())
        return
    
    text = f"👥 <b>Sizning guruhlaringiz</b> ({len(groups)} ta)\n\nGuruhni tanlang:"
    
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=f"👥 {group.name}",
            callback_data=f"group_open:{group.id}",
        )
    builder.button(text="🔙 Orqaga", callback_data="menu:main")
    builder.adjust(1)
    
    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("group_open:"))
async def callback_group_open(callback: CallbackQuery, user: User) -> None:
    """Guruh admin panelini ochish"""
    group_id = int(callback.data.split(":")[1])
    
    from database.models import Group
    async with get_session() as session:
        role = await TaskService.get_user_role_in_group(session, user.id, group_id)
        if not role:
            await callback.answer("🚫 Siz bu guruh a'zosi emassiz", show_alert=True)
            return
        
        stats = await GroupService.get_group_stats(session, group_id)
        
        result = await session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        
        if not group:
            await callback.answer("❗ Guruh topilmadi", show_alert=True)
            return
    
    role_emoji = {
        UserRole.ADMIN: "👑",
        UserRole.MANAGER: "🎯",
        UserRole.EXECUTOR: "👤",
    }
    
    text = (
        f"👥 <b>{group.name}</b>\n\n"
        f"{role_emoji.get(role, '👤')} Sizning rolingiz: <b>{role.value}</b>\n"
        f"👥 A'zolar: <b>{stats['members_count']}</b>\n"
        f"📌 Vazifalar: <b>{stats['total_tasks']}</b>\n"
        f"✅ Bajarilgan: <b>{stats['status_counts'].get('done', 0)}</b>\n"
        f"⏰ Kechikkan: <b>{stats['overdue_count']}</b>\n"
        f"📈 Bajarilish: <b>{stats['completion_rate']}%</b>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=group_admin_keyboard(group_id),
    )
    await callback.answer()


@router.message(Command("members"))
async def cmd_members(message: Message, user: User) -> None:
    """Guruh a'zolari ro'yxati"""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("ℹ️ Bu buyruq faqat guruhda ishlaydi.")
        return
    
    async with get_session() as session:
        group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
        if not group:
            await message.answer("❗ Guruh ro'yxatdan o'tmagan. /start yuboring.")
            return
        
        members = await GroupService.get_members(session, group.id)
    
    if not members:
        await message.answer("👥 Guruhda a'zolar yo'q.")
        return
    
    role_emoji = {
        UserRole.ADMIN: "👑",
        UserRole.MANAGER: "🎯",
        UserRole.EXECUTOR: "👤",
    }
    
    text = f"👥 <b>{group.name}</b> a'zolari ({len(members)} ta)\n\n"
    
    for member in members:
        emoji = role_emoji.get(member.role, "👤")
        username = f" @{member.user.username}" if member.user.username else ""
        text += f"{emoji} <b>{member.user.full_name}</b>{username}\n"
    
    await message.answer(text)


@router.callback_query(F.data.startswith("group_members:"))
async def callback_group_members(callback: CallbackQuery, user: User) -> None:
    """Guruh a'zolari admin paneldan"""
    group_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        members = await GroupService.get_members(session, group_id)
    
    if not members:
        await callback.answer("👥 Hozircha a'zolar yo'q", show_alert=True)
        return
    
    role_emoji = {
        UserRole.ADMIN: "👑",
        UserRole.MANAGER: "🎯",
        UserRole.EXECUTOR: "👤",
    }
    
    text = f"👥 <b>Guruh a'zolari</b> ({len(members)} ta)\n\n"
    for member in members:
        emoji = role_emoji.get(member.role, "👤")
        username = f" @{member.user.username}" if member.user.username else ""
        text += f"{emoji} <b>{member.user.full_name}</b>{username}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data=f"group_open:{group_id}")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("group_stats:"))
async def callback_group_stats(callback: CallbackQuery, user: User, bot: Bot) -> None:
    """Guruh statistikasi callback orqali"""
    group_id = int(callback.data.split(":")[1])
    await callback.answer("⏳ Chart tayyorlanmoqda...")
    
    async with get_session() as session:
        group_stats = await GroupService.get_group_stats(session, group_id)
        member_stats = await StatsService.get_group_member_stats(
            session, group_id, days=30
        )
    
    if group_stats["total_tasks"] == 0:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data=f"group_open:{group_id}")
        await callback.message.edit_text(
            "📊 Guruhda hali vazifalar yo'q.",
            reply_markup=builder.as_markup(),
        )
        return
    
    chart_bytes = generate_overdue_chart(member_stats, group_stats["status_counts"])
    chart_file = BufferedInputFile(chart_bytes, filename="group_stats.png")
    
    caption = (
        f"📊 <b>Guruh statistikasi</b>\n\n"
        f"👥 A'zolar: <b>{group_stats['members_count']}</b>\n"
        f"📌 Vazifalar: <b>{group_stats['total_tasks']}</b>\n"
        f"⏰ Kechikkan: <b>{group_stats['overdue_count']}</b>\n"
        f"📈 Bajarilish: <b>{group_stats['completion_rate']}%</b>"
    )
    
    await callback.message.answer_photo(photo=chart_file, caption=caption)


@router.callback_query(F.data.startswith("group_tasks:"))
async def callback_group_tasks(callback: CallbackQuery, user: User) -> None:
    """Guruh vazifalari"""
    group_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        tasks = await TaskService.get_group_tasks(session, group_id)
    
    if not tasks:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data=f"group_open:{group_id}")
        await callback.message.edit_text(
            "📋 Guruhda hali vazifalar yo'q.\n\n"
            "<i>Yangi vazifa yaratish uchun /newtask</i>",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"📋 <b>Guruh vazifalari</b> ({len(tasks)} ta)\n\nVazifani tanlang:",
        reply_markup=task_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_settings:"))
async def callback_group_settings(callback: CallbackQuery, user: User) -> None:
    """Guruh sozlamalari"""
    group_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        role = await TaskService.get_user_role_in_group(session, user.id, group_id)
        if role != UserRole.ADMIN:
            await callback.answer("🚫 Faqat admin guruh sozlamalarini o'zgartira oladi", show_alert=True)
            return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data=f"group_open:{group_id}")
    
    await callback.message.edit_text(
        "⚙️ <b>Guruh sozlamalari</b>\n\n"
        "<i>Bu funksiya ishlab chiqilmoqda.</i>",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_report:"))
async def callback_group_report(callback: CallbackQuery, user: User, bot: Bot) -> None:
    """Guruh haftalik hisoboti"""
    group_id = int(callback.data.split(":")[1])
    await callback.answer("⏳ Hisobot tayyorlanmoqda...")
    
    async with get_session() as session:
        role = await TaskService.get_user_role_in_group(session, user.id, group_id)
        if role not in (UserRole.ADMIN, UserRole.MANAGER):
            await callback.answer("🚫 Faqat admin/menejerlar uchun", show_alert=True)
            return
        
        member_stats = await StatsService.get_group_member_stats(
            session, group_id, days=30
        )
        weekly = await StatsService.get_weekly_dynamics(session, group_id=group_id)
        completion_report = await StatsService.get_completion_report(
            session, group_id=group_id, days=7
        )
    
    if completion_report["total_created"] == 0 and completion_report["total_completed"] == 0:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data=f"group_open:{group_id}")
        await callback.message.edit_text(
            "📑 Hali hisobot uchun ma'lumot yetarli emas.",
            reply_markup=builder.as_markup(),
        )
        return
    
    chart_bytes = generate_group_report_chart(member_stats, weekly, completion_report)
    chart_file = BufferedInputFile(chart_bytes, filename="group_report.png")
    
    caption = (
        f"📑 <b>Haftalik hisobot</b>\n\n"
        f"📊 <b>So'nggi 7 kun:</b>\n"
        f"📌 Yaratildi: {completion_report['total_created']}\n"
        f"✅ Bajarildi: {completion_report['total_completed']}\n"
        f"⏰ Kechikdi: {completion_report['total_overdue']}\n"
        f"📈 Bajarilish: {completion_report['completion_rate']}%\n"
        f"⏱ O'rtacha bajarish: {completion_report['avg_completion_hours']} soat"
    )
    
    await callback.message.answer_photo(photo=chart_file, caption=caption)


async def _ensure_user(session, tg_user):
    """Telegram user -> DB user (yaratadi yoki topadi)"""
    if not tg_user or tg_user.is_bot:
        return None
    res = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    db_u = res.scalar_one_or_none()
    if not db_u:
        db_u = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name or "Noma'lum",
        )
        session.add(db_u)
        await session.flush()
    return db_u


async def _sync_member_to_company(session, company_id, user_id, role=CompanyRole.MEMBER):
    """CompanyMember ga qo'shish"""
    res = await session.execute(
        select(CompanyMember).where(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == user_id,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        if role == CompanyRole.OWNER and existing.role != CompanyRole.OWNER:
            existing.role = role
        return existing
    m = CompanyMember(company_id=company_id, user_id=user_id, role=role)
    session.add(m)
    await session.flush()
    return m


@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_bot_added_to_group(event: ChatMemberUpdated, bot: Bot) -> None:
    """Bot guruhga qo'shilganda — avtomatik jamoa (Company) yaratamiz"""
    if event.chat.type not in ("group", "supergroup"):
        return

    logger.info(f"Bot guruhga qo'shildi: {event.chat.id} - {event.chat.title}")

    try:
        async with get_session() as session:
            adder = await _ensure_user(session, event.from_user)
            if not adder:
                return

            group = await GroupService.create_or_get_group(
                session, event.chat.id, event.chat.title or "Guruh", adder.id
            )

            # Linked company yaratamiz
            if not group.company_id:
                company = await CompanyService.create_company(
                    session, event.chat.title or "Guruh", adder.id
                )
                group.company_id = company.id
                await session.flush()

            await _sync_member_to_company(session, group.company_id, adder.id, CompanyRole.OWNER)

            # Telegram admin'larni avtomatik qo'shamiz
            try:
                admins = await bot.get_chat_administrators(event.chat.id)
                for adm in admins:
                    if adm.user.is_bot:
                        continue
                    db_adm = await _ensure_user(session, adm.user)
                    if not db_adm:
                        continue
                    role = UserRole.ADMIN if getattr(adm, "status", "") == "creator" else UserRole.MANAGER
                    await GroupService.add_member(session, group.id, db_adm.id, role)
                    c_role = CompanyRole.OWNER if db_adm.id == adder.id else CompanyRole.ADMIN
                    await _sync_member_to_company(session, group.company_id, db_adm.id, c_role)
            except Exception as e:
                logger.warning(f"Adminlarni olishda xato: {e}")
    except Exception as e:
        logger.exception(f"Guruhda auto-jamoa yaratishda xato: {e}")

    await bot.send_message(
        event.chat.id,
        f"👋 Salom, <b>{event.chat.title}</b>!\n\n"
        f"Men <b>TaskBot</b>man. Guruhingiz avtomatik <b>jamoa</b> sifatida ro'yxatdan o'tdi! 🎉\n\n"
        f"👇 <b>Jamoaga qo'shilish uchun har bir a'zo /qoshilish buyrug'ini yuboring!</b>\n\n"
        f"<b>📋 Buyruqlar:</b>\n"
        f"/qoshilish — jamoaga qo'shilish\n"
        f"/newtask — yangi vazifa\n"
        f"/mytasks — mening vazifalarim\n"
        f"/alltasks — barcha vazifalar\n"
        f"/stats — statistika\n"
        f"/members — a'zolar\n"
        f"/overdue — kechikkanlar\n"
        f"/help — yordam",
        parse_mode="HTML",
    )


@router.message(Command("qoshilish"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_join_company(message: Message) -> None:
    """Guruhda /qoshilish — foydalanuvchini jamoaga qo'shish"""
    async with get_session() as session:
        group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
        if not group:
            await message.answer("❗ Bu guruh ro'yxatdan o'tmagan. Admin /start yuboring.")
            return

        tg_user = message.from_user
        if not tg_user or tg_user.is_bot:
            return

        db_user = await _ensure_user(session, tg_user)
        if not db_user:
            return

        # GroupMember
        existing_gm = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.user_id == db_user.id,
            )
        )
        if not existing_gm.scalar_one_or_none():
            await GroupService.add_member(session, group.id, db_user.id, UserRole.EXECUTOR)

        # CompanyMember
        if group.company_id:
            await _sync_member_to_company(session, group.company_id, db_user.id, CompanyRole.MEMBER)

        await session.commit()

    await message.answer(
        f"✅ <b>{message.from_user.full_name}</b>, siz <b>{group.name}</b> "
        f"jamoasiga muvaffaqiyatli qo'shildingiz! 🎉\n\n"
        f"Endi Mini App orqali vazifalaringizni ko'rishingiz mumkin.",
        parse_mode="HTML",
    )


@router.my_chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_bot_removed_from_group(event: ChatMemberUpdated) -> None:
    """Bot guruhdan chiqarilganda"""
    logger.info(f"Bot guruhdan chiqarildi: {event.chat.id}")
    
    try:
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, event.chat.id)
            if group:
                group.is_active = False
    except Exception as e:
        logger.warning(f"Guruh deaktivatsiya xatosi: {e}")


@router.message(F.new_chat_members)
async def on_new_member(message: Message) -> None:
    """Guruhga yangi a'zo qo'shilganda"""
    if message.chat.type not in ("group", "supergroup"):
        return
    
    async with get_session() as session:
        group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
        if not group:
            return
        
        for new_member in message.new_chat_members:
            if new_member.is_bot:
                continue
            
            result = await session.execute(
                select(User).where(User.telegram_id == new_member.id)
            )
            db_user = result.scalar_one_or_none()
            
            if not db_user:
                db_user = User(
                    telegram_id=new_member.id,
                    username=new_member.username,
                    full_name=new_member.full_name or "Noma'lum",
                )
                session.add(db_user)
                await session.flush()
            
            await GroupService.add_member(session, group.id, db_user.id)
            if group.company_id:
                await _sync_member_to_company(session, group.company_id, db_user.id, CompanyRole.MEMBER)

            await message.answer(
                f"👋 Xush kelibsiz, <b>{new_member.full_name}</b>!\n\n"
                f"Endi siz <b>{group.name}</b> jamoasiga qo'shildingiz. 🎉\n"
                f"Vazifalaringizni /mytasks orqali ko'rishingiz mumkin.",
                parse_mode="HTML",
            )


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, ~F.text.startswith("/"))
async def on_group_message(message: Message) -> None:
    """Guruhda xabar yozgan har bir a'zoni avtomatik jamoaga qo'shish (buyruqlar bundan mustasno)"""
    if not message.from_user or message.from_user.is_bot:
        return
    # Buyruqlar bu handlerdagi logikani o'tkazib yuboradi (ular alohida handler orqali)
    # Lekin biz faqat foydalanuvchini qo'shishni xohlaymiz — boshqa amallar yo'q
    try:
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if not group or not group.company_id:
                return

            db_user = await _ensure_user(session, message.from_user)
            if not db_user:
                return

            # Already member check
            gm_res = await session.execute(
                select(GroupMember).where(
                    GroupMember.group_id == group.id,
                    GroupMember.user_id == db_user.id,
                )
            )
            if gm_res.scalar_one_or_none():
                return  # Already in group — do nothing

            await GroupService.add_member(session, group.id, db_user.id, UserRole.EXECUTOR)
            await _sync_member_to_company(session, group.company_id, db_user.id, CompanyRole.MEMBER)
            await session.commit()
    except Exception as e:
        logger.warning(f"on_group_message auto-add xatosi: {e}")


# =========================================================
# /newtask — guruh chatida Mini App orqali vazifa yaratish
# =========================================================

@router.message(Command("newtask"), F.chat.type.in_({"group", "supergroup"}))
async def group_newtask(message: Message, user: User) -> None:
    """Guruh chatida /newtask — Mini App WebApp tugmasi yuboradi"""
    from config import settings
    webapp_url = getattr(settings, "WEBAPP_URL", "")

    if not webapp_url:
        await message.answer("❌ Mini App URL sozlanmagan.")
        return

    # Create deep link with create action
    create_url = webapp_url.rstrip("/") + "/?v=67&action=create"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="➕ Vazifa yaratish (Mini App)",
            web_app=WebAppInfo(url=create_url),
        )],
        [InlineKeyboardButton(
            text="📋 Mini App ochish",
            web_app=WebAppInfo(url=webapp_url.rstrip("/") + "/?v=67"),
        )],
    ])

    async with get_session() as session:
        result = await session.execute(
            select(Group).where(Group.telegram_group_id == message.chat.id)
        )
        group = result.scalar_one_or_none()

    group_name = group.name if group else message.chat.title or "Guruh"

    await message.answer(
        f"📝 <b>{group_name}</b> guruhida yangi vazifa yaratish:\n\n"
        f"Mini App orqali vazifani yarating — ijrochilar, deadline va ustuvorlikni belgilang.",
        reply_markup=kb,
    )


# =========================================================
# /leavegroup — guruhdan chiqish
# =========================================================

@router.message(Command("leavegroup"))
async def cmd_leave_group(message: Message, user: User) -> None:
    """Guruhdan chiqish — private yoki guruh chatidan"""
    from sqlalchemy import delete as sql_delete

    # Guruh chatida yozilsa — o'sha guruhdan chiqadi
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            result = await session.execute(
                select(Group).where(Group.telegram_group_id == message.chat.id)
            )
            group = result.scalar_one_or_none()

            if not group:
                await message.answer("❗ Bu guruh ro'yxatda topilmadi.")
                return

            member_res = await session.execute(
                select(GroupMember).where(
                    GroupMember.group_id == group.id,
                    GroupMember.user_id == user.id,
                )
            )
            member = member_res.scalar_one_or_none()

            if not member:
                await message.answer("❗ Siz bu guruh a'zosi emassiz.")
                return

            await session.delete(member)

            # Kompaniya a'zoligini ham olib tashlaymiz (agar faqat shu guruh orqali qo'shilgan bo'lsa)
            if group.company_id:
                other_groups = await session.execute(
                    select(GroupMember).where(
                        GroupMember.user_id == user.id,
                        GroupMember.group_id != group.id,
                    )
                )
                other = other_groups.scalars().all()
                if not other:
                    await session.execute(
                        sql_delete(CompanyMember).where(
                            CompanyMember.company_id == group.company_id,
                            CompanyMember.user_id == user.id,
                        )
                    )

            await session.commit()

        await message.answer(
            f"✅ Siz <b>{group.name}</b> guruhidan muvaffaqiyatli chiqdingiz.",
        )
        return

    # Private chatda — barcha guruhlarini ko'rsatadi, tanlash uchun
    async with get_session() as session:
        groups = await GroupService.get_user_groups(session, user.id)

    if not groups:
        await message.answer("❗ Siz hech qanday guruhga a'zo emassiz.")
        return

    builder = InlineKeyboardBuilder()
    for g in groups:
        builder.button(
            text=f"🚪 {g.name}",
            callback_data=f"leave_group:{g.id}",
        )
    builder.adjust(1)
    builder.button(text="❌ Bekor qilish", callback_data="cancel")

    await message.answer(
        "🚪 <b>Qaysi guruhdan chiqmoqchisiz?</b>\n\n"
        "⚠️ Guruhdan chiqsangiz, shu guruh vazifalarini ko'ra olmaysiz.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("leave_group:"))
async def cb_leave_group(callback: CallbackQuery, user: User) -> None:
    """Guruhdan chiqish tasdiqlash"""
    from sqlalchemy import delete as sql_delete

    group_id = int(callback.data.split(":")[1])

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, chiqaman", callback_data=f"leave_group_confirm:{group_id}")
    builder.button(text="❌ Yo'q", callback_data="cancel")
    builder.adjust(2)

    async with get_session() as session:
        result = await session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()

    await callback.message.edit_text(
        f"❓ <b>{group.name if group else 'Guruh'}</b> guruhidan chiqishni tasdiqlaysizmi?\n\n"
        "Bu guruhning vazifalari sizga ko'rinmay qoladi.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("leave_group_confirm:"))
async def cb_leave_group_confirm(callback: CallbackQuery, user: User) -> None:
    """Guruhdan chiqishni amalga oshirish"""
    from sqlalchemy import delete as sql_delete

    group_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        result = await session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()

        if not group:
            await callback.answer("Guruh topilmadi.", show_alert=True)
            return

        member_res = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user.id,
            )
        )
        member = member_res.scalar_one_or_none()

        if not member:
            await callback.answer("Siz bu guruh a'zosi emassiz.", show_alert=True)
            return

        await session.delete(member)

        if group.company_id:
            await session.execute(
                sql_delete(CompanyMember).where(
                    CompanyMember.company_id == group.company_id,
                    CompanyMember.user_id == user.id,
                )
            )

        # Get remaining members to notify
        remaining_res = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id != user.id,
            )
        )
        remaining_members = remaining_res.scalars().all()

        await session.commit()
        group_name = group.name

    await callback.message.edit_text(
        f"✅ Siz <b>{group_name}</b> guruhidan chiqdingiz.\n\n"
        "Guruh vazifalari ro'yxatdan olib tashlandi."
    )
    await callback.answer()

    # Notify remaining members
    notify_text = (
        f"🚪 <b>{user.full_name}</b> "
        f"<b>{group_name}</b> guruhidan chiqdi."
    )
    for rem in remaining_members:
        try:
            await callback.bot.send_message(
                rem.user_id,
                notify_text,
                parse_mode="HTML",
            )
        except Exception:
            pass
