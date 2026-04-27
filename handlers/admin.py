"""
Admin handler - super admin (tizim egasi) uchun
"""
import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from config import settings
from database.db import get_session
from database.models import User, Group, Task, TaskStatus
from keyboards.inline import back_to_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


def is_super_admin(user_id: int) -> bool:
    """Super admin tekshiruvi"""
    return user_id in settings.admin_ids_list


@router.message(Command("admin"))
async def cmd_admin(message: Message, user: User) -> None:
    """Admin paneli"""
    if not is_super_admin(user.telegram_id):
        return
    
    async with get_session() as session:
        users_count = (await session.execute(
            select(func.count(User.id))
        )).scalar()
        
        banned_count = (await session.execute(
            select(func.count(User.id)).where(User.is_banned == True)
        )).scalar()
        
        groups_count = (await session.execute(
            select(func.count(Group.id)).where(Group.is_active == True)
        )).scalar()
        
        tasks_count = (await session.execute(
            select(func.count(Task.id))
        )).scalar()
        
        active_tasks = (await session.execute(
            select(func.count(Task.id)).where(
                Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])
            )
        )).scalar()
    
    text = (
        f"👑 <b>Admin panel</b>\n\n"
        f"📊 <b>Umumiy statistika:</b>\n"
        f"👤 Foydalanuvchilar: <b>{users_count}</b>\n"
        f"🚫 Bloklangan: <b>{banned_count}</b>\n"
        f"👥 Faol guruhlar: <b>{groups_count}</b>\n"
        f"📋 Jami vazifalar: <b>{tasks_count}</b>\n"
        f"⚙️ Faol vazifalar: <b>{active_tasks}</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Broadcast", callback_data="admin:broadcast")
    builder.button(text="🚫 Bloklash", callback_data="admin:ban")
    builder.button(text="✅ Blokdan chiqarish", callback_data="admin:unban")
    builder.button(text="📊 Batafsil stats", callback_data="admin:stats")
    builder.adjust(2)
    
    await message.answer(text, reply_markup=builder.as_markup())


# ===== Admin callback handlerlar =====

@router.callback_query(F.data == "admin:broadcast")
async def callback_admin_broadcast(callback: CallbackQuery, user: User) -> None:
    """Broadcast haqida yo'riqnoma"""
    if not is_super_admin(user.telegram_id):
        return
    await callback.answer(
        "📢 Broadcast uchun:\n"
        "Xabar yozing va unga reply qilib\n"
        "/broadcast buyrug'ini yuboring.",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:ban")
async def callback_admin_ban(callback: CallbackQuery, user: User) -> None:
    """Ban haqida yo'riqnoma"""
    if not is_super_admin(user.telegram_id):
        return
    await callback.answer(
        "🚫 Bloklash uchun:\n"
        "/ban <telegram_user_id>\n"
        "Masalan: /ban 123456789",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:unban")
async def callback_admin_unban(callback: CallbackQuery, user: User) -> None:
    """Unban haqida yo'riqnoma"""
    if not is_super_admin(user.telegram_id):
        return
    await callback.answer(
        "✅ Blokdan chiqarish uchun:\n"
        "/unban <telegram_user_id>\n"
        "Masalan: /unban 123456789",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:stats")
async def callback_admin_stats(callback: CallbackQuery, user: User) -> None:
    """Batafsil admin statistika (inline)"""
    if not is_super_admin(user.telegram_id):
        return
    
    async with get_session() as session:
        total_users = (await session.execute(
            select(func.count(User.id))
        )).scalar()
        
        active_groups = (await session.execute(
            select(func.count(Group.id)).where(Group.is_active == True)
        )).scalar()
        
        result = await session.execute(
            select(Task.status, func.count(Task.id)).group_by(Task.status)
        )
        status_counts = {row[0].value: row[1] for row in result.all()}
        
        from datetime import datetime, timedelta
        last_week = datetime.utcnow() - timedelta(days=7)
        new_users = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= last_week)
        )).scalar()
        
        new_tasks = (await session.execute(
            select(func.count(Task.id)).where(Task.created_at >= last_week)
        )).scalar()
    
    text = (
        f"👑 <b>Batafsil admin statistikasi</b>\n\n"
        f"<b>👥 Foydalanuvchilar:</b>\n"
        f"Jami: {total_users}\n"
        f"Yangi (7 kun): {new_users}\n\n"
        f"<b>📂 Guruhlar:</b>\n"
        f"Faol: {active_groups}\n\n"
        f"<b>📋 Vazifalar holati:</b>\n"
    )
    
    status_names = {
        "new": "🆕 Yangi",
        "in_progress": "⚙️ Jarayonda",
        "review": "🔍 Ko'rilmoqda",
        "done": "✅ Bajarildi",
        "overdue": "⏰ Kechikdi",
        "cancelled": "🚫 Bekor qilindi",
    }
    
    for status, count in status_counts.items():
        name = status_names.get(status, status)
        text += f"{name}: {count}\n"
    
    text += f"\n<b>📈 So'nggi 7 kun:</b>\n"
    text += f"Yangi vazifalar: {new_tasks}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data="menu:main")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


# ===== Admin buyruqlari =====

@router.message(Command("ban"))
async def cmd_ban(message: Message, user: User) -> None:
    """Foydalanuvchini bloklash: /ban <user_id>"""
    if not is_super_admin(user.telegram_id):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❗ Format: <code>/ban user_id</code>")
        return
    
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❗ user_id raqam bo'lishi kerak.")
        return
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        target = result.scalar_one_or_none()
        
        if not target:
            await message.answer("❗ Foydalanuvchi topilmadi.")
            return
        
        target.is_banned = True
    
    await message.answer(f"🚫 <b>{target.full_name}</b> bloklandi.")
    logger.warning(f"User {target_id} banned by admin {user.telegram_id}")


@router.message(Command("unban"))
async def cmd_unban(message: Message, user: User) -> None:
    """Bloklashni olib tashlash"""
    if not is_super_admin(user.telegram_id):
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❗ Format: <code>/unban user_id</code>")
        return
    
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❗ user_id raqam bo'lishi kerak.")
        return
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        target = result.scalar_one_or_none()
        
        if not target:
            await message.answer("❗ Foydalanuvchi topilmadi.")
            return
        
        target.is_banned = False
    
    await message.answer(f"✅ <b>{target.full_name}</b> blokdan chiqarildi.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, user: User) -> None:
    """Barcha foydalanuvchilarga xabar yuborish"""
    if not is_super_admin(user.telegram_id):
        return
    
    if not message.reply_to_message:
        await message.answer(
            "ℹ️ Xabarga <b>reply</b> qilib /broadcast yuboring.\n\n"
            "Misol: Xabar yozing, so'ng unga reply qilib /broadcast yuboring."
        )
        return
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.is_banned == False)
        )
        users = list(result.scalars().all())
    
    sent = 0
    failed = 0
    
    status_msg = await message.answer(f"⏳ Xabar yuborilmoqda... (0/{len(users)})")
    
    for i, target_user in enumerate(users):
        try:
            await message.reply_to_message.copy_to(chat_id=target_user.telegram_id)
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast failed for {target_user.telegram_id}: {e}")
        
        # Telegram rate limit himoyasi
        await asyncio.sleep(0.05)
        
        if (i + 1) % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"⏳ Yuborilmoqda... ({i+1}/{len(users)})\n"
                    f"✅ Muvaffaqiyatli: {sent}\n"
                    f"❌ Xato: {failed}"
                )
            except Exception:
                pass
    
    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast yakunlandi</b>\n\n"
            f"📊 Natija:\n"
            f"✅ Yuborildi: {sent}\n"
            f"❌ Xato: {failed}\n"
            f"📱 Jami: {len(users)}"
        )
    except Exception:
        pass


@router.message(Command("stats_admin"))
async def cmd_admin_stats(message: Message, user: User) -> None:
    """Admin uchun batafsil statistika"""
    if not is_super_admin(user.telegram_id):
        return
    
    async with get_session() as session:
        total_users = (await session.execute(
            select(func.count(User.id))
        )).scalar()
        
        active_groups = (await session.execute(
            select(func.count(Group.id)).where(Group.is_active == True)
        )).scalar()
        
        result = await session.execute(
            select(Task.status, func.count(Task.id)).group_by(Task.status)
        )
        status_counts = {row[0].value: row[1] for row in result.all()}
        
        from datetime import datetime, timedelta
        last_week = datetime.utcnow() - timedelta(days=7)
        new_users = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= last_week)
        )).scalar()
        
        new_tasks = (await session.execute(
            select(func.count(Task.id)).where(Task.created_at >= last_week)
        )).scalar()
    
    status_names = {
        "new": "🆕 Yangi",
        "in_progress": "⚙️ Jarayonda",
        "review": "🔍 Ko'rilmoqda",
        "done": "✅ Bajarildi",
        "overdue": "⏰ Kechikdi",
        "cancelled": "🚫 Bekor qilindi",
    }
    
    text = (
        f"👑 <b>Admin statistikasi</b>\n\n"
        f"<b>👥 Foydalanuvchilar:</b>\n"
        f"Jami: {total_users}\n"
        f"Yangi (7 kun): {new_users}\n\n"
        f"<b>📂 Guruhlar:</b>\n"
        f"Faol: {active_groups}\n\n"
        f"<b>📋 Vazifalar holati:</b>\n"
    )
    
    for status, count in status_counts.items():
        name = status_names.get(status, status)
        text += f"{name}: {count}\n"
    
    text += f"\n<b>📈 So'nggi 7 kun:</b>\n"
    text += f"Yangi vazifalar: {new_tasks}"
    
    await message.answer(text)
