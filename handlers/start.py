"""
Start handler - /start, ro'yxatdan o'tish, til tanlash, yordam
"""
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from config import settings
from database.db import get_session
from database.models import User, CompanyRole
from keyboards.inline import main_menu_keyboard, language_keyboard
from keyboards.reply import main_reply_keyboard
from services.group_service import GroupService
from services.company_service import CompanyService

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User, command: CommandObject) -> None:
    """Bot ishga tushirish"""
    await state.clear()

    args = command.args

    # QR / deep-link orqali to'g'ridan-to'g'ri murojaat oqimini ochish
    if args in ("murojaat", "feedback") and message.chat.type == "private":
        from handlers.feedback import feedback_start
        await feedback_start(message, state, user)
        return

    if args and args.startswith("c_"):
        invite_code = args[2:]
        async with get_session() as session:
            company = await CompanyService.get_company_by_invite(session, invite_code)
            if company:
                member = await CompanyService.add_member(session, company.id, user.id, CompanyRole.MEMBER)
                await message.answer(f"🎉 <b>Tabriklaymiz!</b> Siz <b>{company.name}</b> kompaniyasiga xodim sifatida qo'shildingiz.")
            else:
                await message.answer("❌ Taklif havolasi yaroqsiz yoki eskirgan.")
    
    
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.create_or_get_group(
                session=session,
                telegram_group_id=message.chat.id,
                name=message.chat.title or "Guruh",
                owner_id=user.id,
            )
            await GroupService.add_member(session, group.id, user.id)
        
        await message.answer(
            f"👋 Salom, <b>{message.chat.title}</b>!\n\n"
            f"Men <b>TaskBot</b> - jamoangiz uchun vazifalar boshqaruvi botiman.\n\n"
            f"🎯 <b>Men nima qila olaman:</b>\n"
            f"• Vazifalar yaratish va taqsimlash\n"
            f"• Deadline kuzatish va ogohlantirish\n"
            f"• Statistika va chart ko'rsatish\n"
            f"• Kechikishlarni aniqlash\n\n"
            f"📋 /newtask - yangi vazifa\n"
            f"📊 /stats - statistika\n"
            f"❓ /help - yordam"
        )
        return
    
    from i18n import t
    lang = user.language or "uz"
    text = (
        f"{t('start.welcome_title', lang, name=user.full_name)}\n\n"
        f"{t('start.welcome_body', lang)}"
    )

    await message.answer(text, reply_markup=main_menu_keyboard(lang=lang))
    tip = {
        "uz": "💡 <b>Maslahat:</b> Meni o'z guruhingizga qo'shing!",
        "ru": "💡 <b>Совет:</b> Добавьте меня в свою группу!",
        "en": "💡 <b>Tip:</b> Add me to your group!",
    }.get(lang, "💡")
    await message.answer(tip, reply_markup=main_reply_keyboard(lang=lang))


@router.message(Command("app"))
@router.message(Command("miniapp"))
@router.message(F.text.in_({"📱 TaskBot ilovasi", "📱 Приложение TaskBot", "📱 TaskBot App"}))
async def cmd_open_app(message: Message, user: User) -> None:
    """Mini App ni ochish — token bilan (Telegram Desktop da ham ishlaydi)"""
    if not settings.WEBAPP_URL:
        await message.answer("⚠️ Mini App hozircha sozlanmagan.")
        return

    from api.auth import create_auth_token
    token = create_auth_token(
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name or "",
        last_name=message.from_user.last_name or "",
        username=message.from_user.username or "",
    )
    webapp_url = f"{settings.WEBAPP_URL.rstrip('/')}/?v=67&token={token}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📱 Ilovani ochish",
            web_app=WebAppInfo(url=webapp_url),
        )
    ]])
    await message.answer("👇", reply_markup=kb)


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    """Til tanlash"""
    await message.answer(
        "🌐 <b>Tilni tanlang / Выберите язык / Choose language:</b>",
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def callback_language(callback: CallbackQuery, user: User) -> None:
    """Til o'zgartirish — keyin user.language yangilanadi va menyu o'sha tilda chiqadi.

    Mini-app ham `/api/i18n` orqali yangi tilni avtomatik oladi.
    """
    from i18n import t
    from keyboards.reply import main_reply_keyboard

    lang = callback.data.split(":")[1]
    if lang not in ("uz", "ru", "en"):
        await callback.answer("❌")
        return

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.id == user.id)
        )
        db_user = result.scalar_one()
        db_user.language = lang
        user.language = lang

    lang_names = {"uz": t("lang.uz", lang), "ru": t("lang.ru", lang), "en": t("lang.en", lang)}
    await callback.answer(f"✅ {lang_names.get(lang)}")

    changed_text = t("lang.changed", lang, lang=lang_names.get(lang, lang))
    is_private = callback.message.chat.type == "private"

    if is_private:
        # Shaxsiy chatda — full menyu (WebApp tugmasi bilan)
        try:
            await callback.message.edit_text(changed_text, reply_markup=main_menu_keyboard(lang=lang))
        except Exception:
            try:
                await callback.message.answer(changed_text, reply_markup=main_menu_keyboard(lang=lang))
            except Exception:
                pass
        # Reply-keyboard ham yangi tilda yangilansin
        try:
            await callback.message.answer("🔄", reply_markup=main_reply_keyboard(lang=lang))
        except Exception:
            pass
    else:
        # Guruh chatida — WebApp tugmasisiz oddiy matn
        try:
            await callback.message.edit_text(changed_text)
        except Exception:
            pass


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Yordam"""
    help_text = (
        "📚 <b>TaskBot qo'llanmasi</b>\n\n"
        "<b>🎯 Asosiy buyruqlar:</b>\n"
        "/start - Botni ishga tushirish\n"
        "/newtask - Yangi vazifa yaratish\n"
        "/mytasks - Mening vazifalarim\n"
        "/alltasks - Barcha vazifalar\n"
        "/stats - Statistika va chart\n"
        "/overdue - Kechikkan vazifalar\n\n"
        
        "<b>👥 Guruh buyruqlari:</b>\n"
        "/groups - Mening guruhlarim\n"
        "/members - Guruh a'zolari\n"
        "/report - Hisobot olish\n\n"
        
        "<b>⚙️ Boshqalar:</b>\n"
        "/settings - Sozlamalar\n"
        "/language - Tilni o'zgartirish\n"
        "/cancel - Amalni bekor qilish\n"
        "/help - Bu yordam\n\n"
        
        "<b>💡 Ishlash tartibi:</b>\n"
        "1️⃣ Meni o'z guruhingizga qo'shing\n"
        "2️⃣ /newtask orqali vazifa yarating\n"
        "3️⃣ A'zolarga taqsimlang\n"
        "4️⃣ Progressni kuzating\n\n"
        
        "<b>📊 Rollar:</b>\n"
        "👑 Admin - barcha huquqlar\n"
        "🎯 Menejer - vazifa yaratish\n"
        "👤 Kuzatuvchi - vazifalarni bajarish"
    )
    await message.answer(help_text)


@router.callback_query(F.data == "menu:main")
async def callback_main_menu(callback: CallbackQuery, user: User, state: FSMContext) -> None:
    """Asosiy menyuga qaytish — foydalanuvchi tilida"""
    from i18n import t
    await state.clear()

    # Guruh chatida WebApp tugmasi (BUTTON_TYPE_INVALID) ishlamaydi —
    # xabarni o'chirib, private chatga yo'naltirish kerak
    if callback.message.chat.type in ("group", "supergroup"):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer("📱 Asosiy menyu uchun botga /start yuboring", show_alert=False)
        return

    lang = user.language
    titles = {
        "uz": "🏠 <b>Asosiy menyu</b>\n\nKerakli bo'limni tanlang:",
        "ru": "🏠 <b>Главное меню</b>\n\nВыберите нужный раздел:",
        "en": "🏠 <b>Main menu</b>\n\nPick a section:",
    }
    text = titles.get(lang, titles["uz"])
    kb = main_menu_keyboard(lang=lang)
    try:
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb)
        else:
            await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        try:
            await callback.message.answer(text, reply_markup=kb)
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Amalni bekor qilish — xatosiz, guruh va shaxsiy chatlarda ham ishlaydi"""
    await state.clear()
    # Xabarni o'chirishga harakat qilamiz
    try:
        await callback.message.delete()
    except Exception:
        # O'chira olmasak — inline klaviatursiz tahrirlash (WebApp xatosi yo'q)
        try:
            await callback.message.edit_text("❌ Bekor qilindi.")
        except Exception:
            pass
    await callback.answer("❌ Bekor qilindi")
    # Faqat shaxsiy chatda asosiy menyu yuboramiz
    if callback.message.chat.type == "private":
        try:
            await callback.bot.send_message(
                callback.message.chat.id,
                "❌ Amal bekor qilindi.",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass


@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery) -> None:
    """Paginatsiya ko'rsatkichi uchun"""
    await callback.answer()
