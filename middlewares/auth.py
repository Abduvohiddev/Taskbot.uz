"""
Autentifikatsiya middleware - foydalanuvchini DB da tekshiradi va yaratadi
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select

from database import get_session, User

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Foydalanuvchini DB da topadi yoki yangi yaratadi"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
        
        if not tg_user or tg_user.is_bot:
            return await handler(event, data)
        
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == tg_user.id)
                )
                user = result.scalar_one_or_none()
                
                if user is None:
                    user = User(
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                        full_name=tg_user.full_name or "Noma'lum",
                        language=tg_user.language_code if tg_user.language_code in ("uz", "ru", "en") else "uz",
                    )
                    session.add(user)
                    await session.flush()
                    logger.info(f"Yangi foydalanuvchi: {user.telegram_id} ({user.full_name})")
                else:
                    # Ma'lumotlarni yangilash
                    if user.username != tg_user.username:
                        user.username = tg_user.username
                    if user.full_name != tg_user.full_name and tg_user.full_name:
                        user.full_name = tg_user.full_name
                
                if user.is_banned:
                    if isinstance(event, Message):
                        await event.answer("🚫 Sizning hisobingiz bloklangan.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Hisobingiz bloklangan.", show_alert=True)
                    return
                
                # Guruhdan xabar kelsa — avtomatik GroupMember + CompanyMember qo'shish
                if isinstance(event, Message) and event.chat.type in ("group", "supergroup"):
                    try:
                        from database.models import (
                            Group, GroupMember, CompanyMember, CompanyRole, UserRole
                        )
                        g_res = await session.execute(
                            select(Group).where(Group.telegram_group_id == event.chat.id)
                        )
                        group = g_res.scalar_one_or_none()
                        if group:
                            gm_res = await session.execute(
                                select(GroupMember).where(
                                    GroupMember.group_id == group.id,
                                    GroupMember.user_id == user.id,
                                )
                            )
                            if not gm_res.scalar_one_or_none():
                                session.add(GroupMember(
                                    group_id=group.id, user_id=user.id, role=UserRole.EXECUTOR
                                ))
                            if group.company_id:
                                cm_res = await session.execute(
                                    select(CompanyMember).where(
                                        CompanyMember.company_id == group.company_id,
                                        CompanyMember.user_id == user.id,
                                    )
                                )
                                if not cm_res.scalar_one_or_none():
                                    session.add(CompanyMember(
                                        company_id=group.company_id, user_id=user.id,
                                        role=CompanyRole.MEMBER,
                                    ))
                    except Exception as e:
                        logger.warning(f"Auto group-member qo'shishda xato: {e}")

                # User ma'lumotlarini data ga qo'shish
                data["user"] = user
                data["user_id"] = user.id
        except Exception as e:
            logger.exception(f"Auth middleware xatosi: {e}")
            if isinstance(event, Message):
                await event.answer("❗ Xatolik yuz berdi. Iltimos, /start yuboring.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❗ Xatolik yuz berdi", show_alert=True)
            return
        
        return await handler(event, data)
