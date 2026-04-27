"""
Jamoa handlerlari - yangi jamoa yaratish, taklif linklari, jamoalarni ko'rish
"""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database.db import get_session
from database.models import User, Company, CompanyRole
from services.company_service import CompanyService
from keyboards.inline import back_to_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


class CompanyStates(StatesGroup):
    waiting_for_company_name = State()
    waiting_for_member_rename = State()


# Inline Keyboards for Company section
def company_list_keyboard(companies: list[Company]) -> InlineKeyboardMarkup:
    """Foydalanuvchi jamoalari ro'yxati"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    for c in companies:
        builder.button(text=f"🏢 {c.name}", callback_data=f"company_view:{c.id}")
    
    builder.button(text="➕ Yangi jamoa yaratish", callback_data="company_create")
    builder.button(text="🔙 Asosiy menyu", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()

def company_detail_keyboard(company: Company, user_role: CompanyRole) -> InlineKeyboardMarkup:
    """Jamoa ma'lumotlari pulti"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    builder.button(text="👥 Xodimlar", callback_data=f"company_members:{company.id}")
    if user_role in (CompanyRole.OWNER, CompanyRole.ADMIN):
        builder.button(text="🔗 Taklif havolasi", callback_data=f"company_invite:{company.id}")
        builder.button(text="⚙️ Sozlamalar", callback_data=f"company_settings:{company.id}")
    
    builder.button(text="🔙 Orqaga", callback_data="menu:companies")
    builder.adjust(1)
    if user_role in (CompanyRole.OWNER, CompanyRole.ADMIN):
        builder.adjust(2, 1, 1)
    return builder.as_markup()


@router.message(Command("company"))
@router.message(Command("companies"))
async def cmd_companies(message: Message, user: User) -> None:
    """Mening jamoalarim"""
    async with get_session() as session:
        companies = await CompanyService.get_user_companies(session, user.id)
    
    if not companies:
        text = (
            "🏢 <b>Siz hali hech qanday jamoaga a'zo emassiz.</b>\n\n"
            "O'z jamoangizni yarating yoki mavjud jamoaga taklif havolasi orqali qo'shiling."
        )
    else:
        text = "🏢 <b>Mening jamoalarim (Workspaces):</b>\nBoshqarish uchun jamoani tanlang:"
        
    await message.answer(text, reply_markup=company_list_keyboard(companies))


@router.callback_query(F.data == "menu:companies")
async def cb_companies(callback: CallbackQuery, user: User) -> None:
    """Mening jamoalarim (callback)"""
    async with get_session() as session:
        companies = await CompanyService.get_user_companies(session, user.id)
    
    if not companies:
        text = (
            "🏢 <b>Siz hali hech qanday jamoaga a'zo emassiz.</b>\n\n"
            "O'z jamoangizni yarating yoki taklif havolasi orqali qo'shiling."
        )
    else:
        text = "🏢 <b>Mening jamoalarim (Workspaces):</b>\nBoshqarish uchun jamoani tanlang:"
        
    await callback.message.edit_text(text, reply_markup=company_list_keyboard(companies))


@router.callback_query(F.data == "company_create")
async def cb_company_create(callback: CallbackQuery, state: FSMContext) -> None:
    """Jamoa yaratish formasi"""
    await state.set_state(CompanyStates.waiting_for_company_name)
    await callback.message.edit_text(
        "🏢 <b>Yangi jamoa yaratish</b>\n\n"
        "Jamoa (yoki jamoa) nomini kiriting:",
        reply_markup=back_to_menu_keyboard()
    )


@router.message(CompanyStates.waiting_for_company_name)
async def process_company_name(message: Message, state: FSMContext, user: User) -> None:
    """Jamoa yaratilishini saqlash"""
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Nomi kamida 2 ta belgi bo'lishi kerak. Qaytadan kiriting:")
        return
        
    async with get_session() as session:
        company = await CompanyService.create_company(session, name, user.id)
        bot_info = await message.bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start=c_{company.invite_code}"
        
    await state.clear()
    
    text = (
        f"✅ <b>{company.name}</b> muvaffaqiyatli yaratildi!\n\n"
        f"Siz endi bu jamoaning egasisiz.\n"
        f"👥 Xodimlarni taklif qilish uchun quyidagi havolani yuboring:\n"
        f"<code>{invite_link}</code>"
    )
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="🏢 Jamoaga kirish", callback_data=f"company_view:{company.id}")
    
    await message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("company_view:"))
async def cb_company_view(callback: CallbackQuery, user: User) -> None:
    """Bitta jamoa ko'rinishi"""
    company_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        company = await CompanyService.get_company(session, company_id)
        if not company:
            await callback.answer("Jamoa topilmadi!", show_alert=True)
            return
            
        # Rolini aniqlaymiz
        user_role = None
        for member in company.members:
            if member.user_id == user.id:
                user_role = member.role
                break
                
        if not user_role:
            await callback.answer("Siz bu jamoada emassiz!", show_alert=True)
            return
            
        text = (
            f"🏢 <b>{company.name}</b>\n\n"
            f"👑 Rahbar: {company.owner.full_name}\n"
            f"👥 Xodimlar soni: {len(company.members)}\n"
            f"👤 Sizning rolingiz: {user_role.value.capitalize()}"
        )
        if company.description:
            text += f"\n\n📝 Tavsif: {company.description}"
            
        await callback.message.edit_text(text, reply_markup=company_detail_keyboard(company, user_role))


@router.callback_query(F.data.startswith("company_invite:"))
async def cb_company_invite(callback: CallbackQuery, user: User) -> None:
    """Taklif havolasini ko'rsatish"""
    company_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        company = await CompanyService.get_company(session, company_id)
        if not company or company.owner_id != user.id: # faqat admin/owner uchun
            await callback.answer("Sizda ruxsat yo'q!", show_alert=True)
            return
            
        bot_info = await callback.bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start=c_{company.invite_code}"
        
        text = (
            f"🔗 <b>{company.name} uchun taklif havolasi:</b>\n\n"
            f"Ushbu havolani xodimlarga yuboring:\n"
            f"<code>{invite_link}</code>\n\n"
            f"Ular havolani bosgach, to'g'ridan-to'g'ri jamoa xodimiga aylanadilar."
        )
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="🔄 Yangi havola yaratish (Eskisi yopiladi)", callback_data=f"company_regen_invite:{company.id}")
        b.button(text="🔙 Orqaga", callback_data=f"company_view:{company.id}")
        b.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("company_members:"))
async def cb_company_members(callback: CallbackQuery, user: User) -> None:
    """A'zolar ro'yxati — owner/admin uchun boshqaruv tugmalari bilan"""
    company_id = int(callback.data.split(":")[1])
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    async with get_session() as session:
        company = await CompanyService.get_company(session, company_id)
        if not company:
            await callback.answer("Jamoa topilmadi", show_alert=True)
            return

        my_role = None
        for m in company.members:
            if m.user_id == user.id:
                my_role = m.role
                break
        if not my_role:
            await callback.answer("Siz bu jamoada emassiz", show_alert=True)
            return

        is_owner = my_role == CompanyRole.OWNER
        is_admin = my_role in (CompanyRole.OWNER, CompanyRole.ADMIN)

        lines = [f"👥 <b>{company.name}</b> — xodimlar\n"]
        role_emoji = {"owner": "👑", "admin": "⭐", "member": "👤"}
        for m in company.members:
            name = m.display_name or m.user.full_name
            r = m.role.value if hasattr(m.role, "value") else str(m.role)
            emo = role_emoji.get(r, "👤")
            lines.append(f"{emo} <b>{name}</b> — <i>{r}</i>")

        builder = InlineKeyboardBuilder()
        if is_admin:
            for m in company.members:
                if m.role == CompanyRole.OWNER or m.user_id == user.id:
                    continue
                name = m.display_name or m.user.full_name
                builder.button(
                    text=f"✏️ {name[:18]}",
                    callback_data=f"member_rename:{company_id}:{m.user_id}",
                )
                if is_owner:
                    builder.button(
                        text=f"🗑 {name[:18]}",
                        callback_data=f"member_kick:{company_id}:{m.user_id}",
                    )
            builder.adjust(2)
        builder.row(InlineKeyboardButton(
            text="🔙 Orqaga", callback_data=f"company_view:{company_id}"
        ))

    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("member_rename:"))
async def cb_member_rename(callback: CallbackQuery, user: User, state: FSMContext) -> None:
    """A'zo nomini o'zgartirish — nom so'rash"""
    parts = callback.data.split(":")
    company_id = int(parts[1])
    target_user_id = int(parts[2])

    async with get_session() as session:
        role = await CompanyService.is_member(session, company_id, user.id)
        if role not in (CompanyRole.OWNER, CompanyRole.ADMIN):
            await callback.answer("Sizda ruxsat yo'q!", show_alert=True)
            return

    await state.set_state(CompanyStates.waiting_for_member_rename)
    await state.update_data(company_id=company_id, target_user_id=target_user_id)
    await callback.message.edit_text(
        "✏️ <b>A'zo nomini o'zgartirish</b>\n\n"
        "Yangi ismni kiriting (jamoa ichida ko'rinadigan):",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(CompanyStates.waiting_for_member_rename)
async def process_member_rename(message: Message, state: FSMContext, user: User) -> None:
    """Yangi display_name saqlash"""
    new_name = message.text.strip()
    if len(new_name) < 2 or len(new_name) > 100:
        await message.answer("Ism 2-100 belgi bo'lsin. Qaytadan kiriting:")
        return

    data = await state.get_data()
    company_id = data.get("company_id")
    target_user_id = data.get("target_user_id")

    async with get_session() as session:
        role = await CompanyService.is_member(session, company_id, user.id)
        if role not in (CompanyRole.OWNER, CompanyRole.ADMIN):
            await message.answer("❗ Ruxsat yo'q.")
            await state.clear()
            return
        ok = await CompanyService.rename_member(session, company_id, target_user_id, new_name)

    await state.clear()
    if ok:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="👥 Xodimlar", callback_data=f"company_members:{company_id}")
        b.button(text="🔙 Menyu",    callback_data="menu:main")
        b.adjust(2)
        await message.answer(
            f"✅ Nom o'zgartirildi: <b>{new_name}</b>",
            reply_markup=b.as_markup(),
        )
    else:
        await message.answer("❗ A'zo topilmadi.")


@router.callback_query(F.data.startswith("member_kick:"))
async def cb_member_kick(callback: CallbackQuery, user: User) -> None:
    """Kick a'zo — tasdiqlash so'rash"""
    parts = callback.data.split(":")
    company_id = int(parts[1])
    target_user_id = int(parts[2])

    async with get_session() as session:
        role = await CompanyService.is_member(session, company_id, user.id)
        if role != CompanyRole.OWNER:
            await callback.answer("Faqat jamoa egasi o'chirishi mumkin!", show_alert=True)
            return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'chirish",
             callback_data=f"member_kick_confirm:{company_id}:{target_user_id}")
    b.button(text="❌ Bekor qilish",
             callback_data=f"company_members:{company_id}")
    b.adjust(1)
    await callback.message.edit_text(
        "⚠️ <b>Tasdiqlang</b>\n\n"
        "Bu a'zoni jamoadan o'chirmoqchimisiz? Uning vazifalari saqlanib qoladi.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data.startswith("member_kick_confirm:"))
async def cb_member_kick_confirm(callback: CallbackQuery, user: User) -> None:
    """Kick tasdiqlandi — o'chirish"""
    parts = callback.data.split(":")
    company_id = int(parts[1])
    target_user_id = int(parts[2])

    async with get_session() as session:
        role = await CompanyService.is_member(session, company_id, user.id)
        if role != CompanyRole.OWNER:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return
        ok = await CompanyService.remove_member(session, company_id, target_user_id)

    if ok:
        await callback.answer("✅ A'zo o'chirildi", show_alert=True)
        callback.data = f"company_members:{company_id}"
        await cb_company_members(callback, user)
    else:
        await callback.answer("❗ O'chirib bo'lmadi", show_alert=True)


@router.callback_query(F.data.startswith("company_regen_invite:"))
async def cb_company_regen_invite(callback: CallbackQuery, user: User) -> None:
    company_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        company = await CompanyService.get_company(session, company_id)
        if not company or company.owner_id != user.id:
            await callback.answer("Ruxsatsiz amal!", show_alert=True)
            return
            
        new_code = await CompanyService.generate_new_invite(session, company.id)
        bot_info = await callback.bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start=c_{new_code}"
        
        text = (
            f"✅ <b>Yangi taklif havolasi yaratildi!</b>\n\n"
            f"Eski havola endi ishlamaydi.\n"
            f"<code>{invite_link}</code>"
        )
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        b = InlineKeyboardBuilder()
        b.button(text="🔙 Orqaga", callback_data=f"company_view:{company.id}")
        await callback.message.edit_text(text, reply_markup=b.as_markup())
