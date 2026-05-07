"""
Tasks handler - vazifalar yaratish, ko'rish, status o'zgartirish
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_session
from database.models import User, TaskStatus, Priority, UserRole, TaskAttachment, Company, Group
from config import settings

_TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
from keyboards.inline import (
    priority_keyboard, deadline_keyboard, assignee_keyboard,
    multi_assignee_keyboard, workspace_picker_keyboard,
    task_actions_keyboard, task_list_keyboard, filter_tasks_keyboard,
    confirm_keyboard, cancel_keyboard, back_to_menu_keyboard,
    group_picker_keyboard, ext_members_keyboard,
)
from services.task_service import TaskService
from services.group_service import GroupService
from services.company_service import CompanyService
from services.notification_service import NotificationService
from utils.helpers import (
    format_task_detailed, format_task_short, parse_datetime,
    PRIORITY_EMOJI, PRIORITY_NAMES_UZ,
)

router = Router()
logger = logging.getLogger(__name__)


class NewTaskStates(StatesGroup):
    """Yangi vazifa yaratish bosqichlari"""
    waiting_title = State()
    waiting_description = State()
    waiting_attachments = State()
    waiting_priority = State()
    waiting_deadline = State()
    waiting_custom_deadline = State()
    waiting_workspace = State()
    waiting_assignee = State()
    waiting_multi_assignee = State()
    waiting_responsible = State()     # Masul tanlash
    waiting_subtask_title = State()   # Sub-task yaratish


def _attach_prompt_text(files_count: int = 0) -> str:
    suffix = f"\n\n📎 <b>Qo'shildi:</b> {files_count} ta fayl" if files_count else ""
    return (
        "📎 <b>3/6 qadam:</b> Fayl, rasm yoki video yuboring.\n\n"
        "• Bir nechta fayl yuborishingiz mumkin\n"
        "• Tayyor bo'lsangiz /done yuboring\n"
        "• O'tkazib yuborish uchun /skip"
        + suffix
    )


def _attach_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tayyor", callback_data="attach:done"),
         InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="attach:skip")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])


@router.message(F.text == "➕ Yangi vazifa")
@router.callback_query(F.data == "menu:newtask")
async def cmd_new_task(event, state: FSMContext, user: User) -> None:
    """Yangi vazifa yaratishni boshlash — rejim tanlash"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    # Avvalgi holatni tozalash
    await state.clear()

    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
    else:
        message = event

    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if group:
                await state.update_data(group_id=group.id, group_telegram_id=message.chat.id)

    text = (
        "🆕 <b>Yangi vazifa yaratish</b>\n\n"
        "Qaysi turdagi vazifa kerak?\n\n"
        "• <b>📝 Oddiy</b> — bir yoki bir nechta odamga biriktiriladi, hammasi parallel ishlaydi\n\n"
        "• <b>🔗 Workflow (ketma-ket)</b> — qadamlar tartibi bilan. "
        "Birinchi odam tugatmaguncha ikkinchisi boshlamaydi"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Oddiy vazifa", callback_data="newtask:simple")],
        [InlineKeyboardButton(text="🔗 Workflow (ketma-ket)", callback_data="newtask:workflow")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])

    if isinstance(event, CallbackQuery):
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "newtask:simple")
async def cb_newtask_simple(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Oddiy vazifa rejimi"""
    await state.set_state(NewTaskStates.waiting_title)
    text = (
        "📝 <b>Oddiy vazifa yaratish</b>\n\n"
        "1/6 qadam: Vazifa <b>nomini</b> kiriting:\n\n"
        "<i>Masalan: Marketing rejasini tayyorlash</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=cancel_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "newtask:workflow")
async def cb_newtask_workflow(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Workflow rejimi — workflow handleriga o'tkazish"""
    from handlers.workflow import WorkflowStates
    await state.clear()
    await state.set_state(WorkflowStates.waiting_title)
    await state.update_data(steps=[])
    text = (
        "🔗 <b>Workflow vazifa yaratish</b>\n\n"
        "Bu rejim — vazifa <i>ketma-ket</i> bajariladi.\n"
        "Birinchi odam o'z qismini tugatmaguncha keyingisi boshlanmaydi.\n\n"
        "1-qadam: Vazifa <b>nomini</b> kiriting:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=cancel_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(NewTaskStates.waiting_title)
async def process_title(message: Message, state: FSMContext) -> None:
    """Vazifa nomi qabul qilish"""
    if not message.text:
        await message.answer("❗ Iltimos, matn yuboring.")
        return
    
    if len(message.text) < 3:
        await message.answer("❗ Vazifa nomi juda qisqa. Kamida 3 belgi bo'lsin.")
        return
    
    if len(message.text) > 500:
        await message.answer("❗ Vazifa nomi juda uzun. Maksimum 500 belgi.")
        return
    
    await state.update_data(title=message.text)
    await state.set_state(NewTaskStates.waiting_description)
    await message.answer(
        "📝 <b>2/6 qadam:</b> Tavsif kiriting.\n\n"
        "<i>O'tkazib yuborish uchun /skip yuboring</i>",
        reply_markup=cancel_keyboard(),
    )


@router.message(NewTaskStates.waiting_description, Command("skip"))
async def skip_description(message: Message, state: FSMContext) -> None:
    """Tavsifni o'tkazib yuborish"""
    await state.update_data(description=None, attachments=[])
    await state.set_state(NewTaskStates.waiting_attachments)
    await message.answer(_attach_prompt_text(0), reply_markup=_attach_keyboard())


@router.message(NewTaskStates.waiting_description)
async def process_description(message: Message, state: FSMContext) -> None:
    """Tavsifni qabul qilish"""
    if not message.text:
        await message.answer("❗ Iltimos, matn yuboring.")
        return

    if len(message.text) > 2000:
        await message.answer("❗ Tavsif juda uzun. Maksimum 2000 belgi.")
        return

    await state.update_data(description=message.text, attachments=[])
    await state.set_state(NewTaskStates.waiting_attachments)
    await message.answer(_attach_prompt_text(0), reply_markup=_attach_keyboard())


# ===== Fayl/rasm/video qabul qilish =====

@router.message(NewTaskStates.waiting_attachments, Command("skip"))
async def skip_attachments(message: Message, state: FSMContext) -> None:
    """Fayllarni o'tkazib yuborish"""
    await state.update_data(attachments=[])
    await state.set_state(NewTaskStates.waiting_priority)
    await message.answer(
        "⚡ <b>4/6 qadam:</b> Muhimlik darajasini tanlang:",
        reply_markup=priority_keyboard(),
    )


@router.message(NewTaskStates.waiting_attachments, Command("done"))
async def done_attachments(message: Message, state: FSMContext) -> None:
    """Fayllarni biriktirishni tugatish"""
    data = await state.get_data()
    atts = data.get("attachments") or []
    await state.set_state(NewTaskStates.waiting_priority)
    await message.answer(
        f"✅ <b>{len(atts)} ta fayl</b> biriktirildi.\n\n"
        "⚡ <b>4/6 qadam:</b> Muhimlik darajasini tanlang:",
        reply_markup=priority_keyboard(),
    )


@router.callback_query(NewTaskStates.waiting_attachments, F.data == "attach:skip")
async def cb_skip_attachments(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(attachments=[])
    await state.set_state(NewTaskStates.waiting_priority)
    await callback.message.edit_text(
        "⚡ <b>4/6 qadam:</b> Muhimlik darajasini tanlang:",
        reply_markup=priority_keyboard(),
    )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_attachments, F.data == "attach:done")
async def cb_done_attachments(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    atts = data.get("attachments") or []
    await state.set_state(NewTaskStates.waiting_priority)
    await callback.message.edit_text(
        f"✅ <b>{len(atts)} ta fayl</b> biriktirildi.\n\n"
        "⚡ <b>4/6 qadam:</b> Muhimlik darajasini tanlang:",
        reply_markup=priority_keyboard(),
    )
    await callback.answer()


@router.message(
    NewTaskStates.waiting_attachments,
    F.content_type.in_({"photo", "video", "document", "audio", "voice", "animation"})
)
async def process_attachment(message: Message, state: FSMContext) -> None:
    """Fayl, rasm, video yoki hujjatni qabul qilish"""
    data = await state.get_data()
    atts = data.get("attachments") or []

    if len(atts) >= 10:
        await message.answer("⚠️ Maksimum 10 ta fayl biriktirish mumkin. /done bosing.")
        return

    file_id = None
    file_type = "document"
    file_name = None
    file_size = None
    mime_type = None

    if message.photo:
        biggest = max(message.photo, key=lambda p: (p.width or 0) * (p.height or 0))
        file_id = biggest.file_id
        file_type = "photo"
        file_name = f"photo_{biggest.file_unique_id}.jpg"
        file_size = biggest.file_size
        mime_type = "image/jpeg"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        file_name = message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
        file_size = message.video.file_size
        mime_type = message.video.mime_type or "video/mp4"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name or f"doc_{message.document.file_unique_id}"
        file_size = message.document.file_size
        mime_type = message.document.mime_type
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
        file_name = message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
        file_size = message.audio.file_size
        mime_type = message.audio.mime_type or "audio/mpeg"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"
        file_name = f"voice_{message.voice.file_unique_id}.ogg"
        file_size = message.voice.file_size
        mime_type = "audio/ogg"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "video"
        file_name = message.animation.file_name or f"gif_{message.animation.file_unique_id}.mp4"
        file_size = message.animation.file_size
        mime_type = message.animation.mime_type or "video/mp4"

    if not file_id:
        await message.answer("❗ Faylni aniqlab bo'lmadi. Qayta urinib ko'ring.")
        return

    # Hajm limiti — 50MB
    if file_size and file_size > 50 * 1024 * 1024:
        await message.answer(f"⚠️ Fayl juda katta ({file_size // 1024 // 1024} MB). Maksimum 50MB.")
        return

    atts.append({
        "file_id": file_id,
        "file_type": file_type,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
    })
    await state.update_data(attachments=atts)

    type_emoji = {"photo": "🖼", "video": "🎥", "document": "📄",
                  "audio": "🎵", "voice": "🎙", "animation": "🎞"}.get(file_type, "📎")
    await message.answer(
        f"{type_emoji} <b>{file_name}</b> qo'shildi ({len(atts)}/10).\n\n"
        "Yana yuboring yoki /done bosing.",
        reply_markup=_attach_keyboard(),
    )


@router.callback_query(NewTaskStates.waiting_priority, F.data.startswith("priority:"))
async def process_priority(callback: CallbackQuery, state: FSMContext) -> None:
    """Muhimlik darajasini tanlash"""
    priority_value = callback.data.split(":")[1]
    priority = Priority(priority_value)
    
    await state.update_data(priority=priority_value)
    await state.set_state(NewTaskStates.waiting_deadline)
    
    priority_text = f"{PRIORITY_EMOJI[priority]} {PRIORITY_NAMES_UZ[priority]}"
    
    await callback.message.edit_text(
        f"✅ Muhimlik: <b>{priority_text}</b>\n\n"
        f"⏰ <b>5/6 qadam:</b> Deadline ni tanlang:",
        reply_markup=deadline_keyboard(),
    )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_deadline, F.data.startswith("deadline:"))
async def process_deadline(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Deadline tanlash"""
    value = callback.data.split(":")[1]
    
    if value == "custom":
        await state.set_state(NewTaskStates.waiting_custom_deadline)
        _now = datetime.now(_TZ)
        _ex_d  = _now.strftime("%d.%m.%Y")
        _ex_dt = _now.strftime("%d.%m.%Y %H:%M")
        await callback.message.edit_text(
            f"✏️ <b>Deadline kiriting:</b>\n\n"
            f"Misol: <code>{_ex_d}</code> yoki <code>{_ex_dt}</code>\n\n"
            "<i>Faqat shu formatlar qabul qilinadi</i>",
            reply_markup=cancel_keyboard(),
        )
        await callback.answer()
        return
    
    if value == "none":
        await state.update_data(deadline=None)
    else:
        try:
            timestamp = float(value)
            deadline = datetime.fromtimestamp(timestamp, tz=_TZ)
            await state.update_data(deadline=deadline.isoformat())
        except (ValueError, OSError) as e:
            logger.warning(f"Deadline parsing xatosi: {e}")
            await callback.answer("❗ Xato yuz berdi, qaytadan tanlang", show_alert=True)
            return
    
    await _proceed_to_assignee(callback.message, state, user)
    await callback.answer()


@router.message(NewTaskStates.waiting_custom_deadline)
async def process_custom_deadline(message: Message, state: FSMContext, user: User) -> None:
    """Qo'lda kiritilgan deadline ni qabul qilish"""
    if not message.text:
        await message.answer("❗ Iltimos, sana kiriting.")
        return
    
    deadline = parse_datetime(message.text)
    
    if not deadline:
        _now = datetime.now(_TZ)
        _ex_d  = _now.strftime("%d.%m.%Y")
        _ex_dt = _now.strftime("%d.%m.%Y %H:%M")
        await message.answer(
            f"❗ Sana formati noto'g'ri.\n\n"
            f"Misol: <code>{_ex_d}</code> yoki <code>{_ex_dt}</code>"
        )
        return
    
    if deadline < datetime.now(_TZ):
        await message.answer("❗ Deadline o'tib ketgan sana bo'lmasligi kerak.")
        return
    
    await state.update_data(deadline=deadline.isoformat())
    await _proceed_to_assignee(message, state, user)


async def _proceed_to_assignee(message: Message, state: FSMContext, user: User) -> None:
    """Ishchi makonni tanlash yoki darhol ijrochi bosqichiga o'tish"""
    data = await state.get_data()
    group_id   = data.get("group_id")
    company_id = data.get("company_id")
    parent_id  = data.get("parent_id")

    # Sub-task yaratilayotganda va kompaniya/guruh allaqachon belgilangan bo'lsa —
    # workspace picker ni o'tkazib, to'g'ridan-to'g'ri ijrochi tanlashga o'tamiz
    if parent_id and company_id and not group_id:
        async with get_session() as session:
            members = await CompanyService.get_members(session, company_id)
        if not members:
            await _create_task_final(message, state, user, [user.id])
            return
        await state.set_state(NewTaskStates.waiting_multi_assignee)
        text = (
            f"👥 <b>Ijrochilarni belgilang</b>\n\n"
            f"<i>Kompaniyada {len(members)} xodim</i>"
        )
        try:
            await message.edit_text(text, reply_markup=multi_assignee_keyboard(members, []))
        except Exception:
            await message.answer(text, reply_markup=multi_assignee_keyboard(members, []))
        return

    # Agar guruh chatidan ochilgan bo'lsa — multi-select + masul tanlash
    if group_id:
        async with get_session() as session:
            members = await GroupService.get_members(session, group_id)
        if not members:
            await message.answer(
                "❗ Guruhda a'zolar yo'q. Avval a'zolarni qo'shing.",
                reply_markup=back_to_menu_keyboard(),
            )
            await state.clear()
            return
        await state.update_data(selected_assignees=[])
        await state.set_state(NewTaskStates.waiting_multi_assignee)
        text = (
            f"👥 <b>Ijrochilarni belgilang</b> (bir nechta tanlash mumkin)\n\n"
            f"<i>Guruhdagi {len(members)} a'zo</i>"
        )
        try:
            await message.edit_text(text, reply_markup=multi_assignee_keyboard(members, []))
        except Exception:
            await message.answer(text, reply_markup=multi_assignee_keyboard(members, []))
        return

    # Shaxsiy chat: foydalanuvchining kompaniya/guruhlarini tekshirib, workspace picker yoki default
    async with get_session() as session:
        companies = await CompanyService.get_user_companies(session, user.id)
        groups = await GroupService.get_user_groups(session, user.id)

    if not companies and not groups:
        await _create_task_final(message, state, user, [user.id])
        return

    await state.set_state(NewTaskStates.waiting_workspace)
    text = (
        "🗂 <b>Vazifa qayerda yaratilsin?</b>\n\n"
        "• 👤 Shaxsiy — faqat siz ko'rasiz\n"
        "• 🏢 Kompaniya — hamkasblar bilan hamkorlik\n"
        "• 👥 Guruh — guruh chatidagi vazifa"
    )
    kb = workspace_picker_keyboard(companies, groups)
    try:
        await message.edit_text(text, reply_markup=kb)
    except Exception:
        await message.answer(text, reply_markup=kb)


@router.callback_query(NewTaskStates.waiting_workspace, F.data.startswith("ws:"))
async def process_workspace(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot) -> None:
    """Workspace (shaxsiy/kompaniya/guruh) tanlash"""
    parts = callback.data.split(":")
    kind = parts[1]

    if kind == "personal":
        await callback.answer()
        await _create_task_final(callback.message, state, user, [user.id], bot=bot)
        return

    if kind == "company":
        company_id = int(parts[2])
        async with get_session() as session:
            role = await CompanyService.is_member(session, company_id, user.id)
            if not role:
                await callback.answer("Siz bu kompaniya a'zosi emassiz", show_alert=True)
                return
            members = await CompanyService.get_members(session, company_id)
        if not members:
            await callback.answer("Kompaniyada xodimlar yo'q", show_alert=True)
            return
        await state.update_data(company_id=company_id, selected_assignees=[])
        await state.set_state(NewTaskStates.waiting_multi_assignee)
        text = (
            f"👥 <b>Ijrochilarni belgilang</b> (bir nechta tanlash mumkin)\n\n"
            f"<i>Kompaniyada {len(members)} xodim</i>"
        )
        await callback.message.edit_text(text, reply_markup=multi_assignee_keyboard(members, []))
        await callback.answer()
        return

    if kind == "group":
        group_id = int(parts[2])
        async with get_session() as session:
            members = await GroupService.get_members(session, group_id)
        if not members:
            await callback.answer("Guruhda a'zolar yo'q", show_alert=True)
            return
        await state.update_data(group_id=group_id, selected_assignees=[])
        await state.set_state(NewTaskStates.waiting_multi_assignee)
        text = (
            f"👥 <b>Ijrochilarni belgilang</b> (bir nechta tanlash mumkin)\n\n"
            f"<i>Guruhdagi {len(members)} a'zo</i>"
        )
        await callback.message.edit_text(
            text, reply_markup=multi_assignee_keyboard(members, [])
        )
        await callback.answer()
        return


async def _render_assignee_msg(callback_or_msg, state: FSMContext, *, answer=False):
    """Assignee tanlov ekranini yangilash yoki yuborish (helper)"""
    data = await state.get_data()
    company_id = data.get("company_id")
    group_id   = data.get("group_id")
    selected = list(data.get("selected_assignees") or [])
    external = list(data.get("external_assignees") or [])
    total = len(selected) + len(external)

    async with get_session() as session:
        if group_id and not company_id:
            members = await GroupService.get_members(session, group_id)
            context_label = f"Guruhdagi {len(members)} a'zo"
        else:
            members = await CompanyService.get_members(session, company_id)
            context_label = f"Kompaniyada {len(members)} xodim"

    new_kb = multi_assignee_keyboard(members, selected, external=external)
    ext_note = f" + {len(external)} tashqi" if external else ""
    text = (
        f"👥 <b>Ijrochilarni belgilang</b> (bir nechta tanlash mumkin)\n\n"
        f"<i>{context_label}{ext_note} — Tanlangan: {total}</i>"
    )
    msg = callback_or_msg if hasattr(callback_or_msg, 'edit_text') else callback_or_msg.message
    if answer:
        await msg.answer(text, reply_markup=new_kb)
    else:
        try:
            await msg.edit_text(text, reply_markup=new_kb)
        except Exception as e:
            if "not modified" not in str(e).lower():
                await msg.answer(text, reply_markup=new_kb)


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data.startswith("assign_toggle:"))
async def process_multi_assignee_toggle(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Kompaniya ijrochilarini belgilash (toggle)"""
    uid = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = list(data.get("selected_assignees") or [])
    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)
    await state.update_data(selected_assignees=selected)
    await _render_assignee_msg(callback.message, state)
    await callback.answer("✅" if uid in selected else "☐")


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data.startswith("assign_toggle_ext:"))
async def process_ext_toggle(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Tashqi guruh a'zosini olib tashlash (toggle — faqat remove)"""
    uid = int(callback.data.split(":")[1])
    data = await state.get_data()
    external = list(data.get("external_assignees") or [])
    external = [e for e in external if e["id"] != uid]
    await state.update_data(external_assignees=external)
    await _render_assignee_msg(callback.message, state)
    await callback.answer("🗑 O'chirildi")


# ─── Boshqa guruhdan qo'shish oqimi ────────────────────────────────────────

@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data == "afg")
async def afg_show_groups(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Boshqa guruhlarni ko'rsatish"""
    data = await state.get_data()
    current_company_id = data.get("company_id")
    async with get_session() as session:
        companies = await CompanyService.get_user_companies(session, user.id)
        groups    = await GroupService.get_user_groups(session, user.id)

    kb = group_picker_keyboard(companies, groups, exclude_company_id=current_company_id)
    await callback.message.edit_text(
        "🏢 <b>Qaysi guruhdan qo'shmoqchisiz?</b>\n\n"
        "<i>Kerakli guruhni tanlang yoki taklif havolasi yuboring</i>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data.startswith("afg_c:"))
async def afg_company_members(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Kompaniya a'zolarini ko'rsatish"""
    company_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = list(data.get("selected_assignees") or [])
    external = list(data.get("external_assignees") or [])
    already_ids = set(selected) | {e["id"] for e in external}

    async with get_session() as session:
        members = await CompanyService.get_members(session, company_id)

    if not members:
        await callback.answer("Bu guruhda a'zolar yo'q", show_alert=True)
        return

    # Company nomini olish
    async with get_session() as session:
        c = await session.get(Company, company_id)
        c_name = c.name if c else f"#{company_id}"

    # State ga joriy ko'rinish uchun company_id saqlash
    await state.update_data(_afg_company_id=company_id, _afg_company_name=c_name)

    kb = ext_members_keyboard(members, already_ids)
    await callback.message.edit_text(
        f"👥 <b>{c_name}</b> — A'zolarni tanlang:\n\n"
        "<i>Tanlangan odamlar taskga qo'shiladi</i>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data.startswith("afg_g:"))
async def afg_group_members(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Guruh (Group) a'zolarini ko'rsatish"""
    group_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = list(data.get("selected_assignees") or [])
    external = list(data.get("external_assignees") or [])
    already_ids = set(selected) | {e["id"] for e in external}

    async with get_session() as session:
        members = await GroupService.get_members(session, group_id)
        g = await session.get(Group, group_id)
        g_name = g.name if g else f"#{group_id}"

    if not members:
        await callback.answer("Bu guruhda a'zolar yo'q", show_alert=True)
        return

    await state.update_data(_afg_group_id=group_id, _afg_company_name=g_name)
    kb = ext_members_keyboard(members, already_ids)
    await callback.message.edit_text(
        f"👥 <b>{g_name}</b> — A'zolarni tanlang:\n\n"
        "<i>Tanlangan odamlar taskga qo'shiladi</i>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data.startswith("afg_add:"))
async def afg_add_member(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Tashqi a'zoni taskga qo'shish"""
    uid = int(callback.data.split(":")[1])
    data = await state.get_data()
    external = list(data.get("external_assignees") or [])

    if any(e["id"] == uid for e in external):
        await callback.answer("Allaqachon qo'shilgan", show_alert=True)
        return

    # User nomini olish
    async with get_session() as session:
        u = await session.get(User, uid)
        name = u.full_name if u else f"#{uid}"

    group_name = data.get("_afg_company_name", "Boshqa guruh")
    external.append({"id": uid, "name": name, "group_name": group_name})
    await state.update_data(external_assignees=external)

    await callback.answer(f"✅ {name} qo'shildi", show_alert=False)
    # Assignee asosiy ekraniga qaytish
    await _render_assignee_msg(callback.message, state)


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data == "afg_back")
async def afg_back(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Asosiy assignee ekraniga qaytish"""
    await _render_assignee_msg(callback.message, state)
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data == "afg_invite")
async def afg_invite(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Taklif havolasini yuborish"""
    from config import settings as _cfg
    bot_username = _cfg.BOT_USERNAME.lstrip("@")
    link = f"https://t.me/{bot_username}?start=invite_{user.id}"
    await callback.message.edit_text(
        f"📨 <b>Taklif havolasi</b>\n\n"
        f"Quyidagi havolani ulashing — odam botga o'tib, jamoangizga qo'shilishi mumkin:\n\n"
        f"<code>{link}</code>\n\n"
        "<i>Havola nusxalandi, do'stingizga yuboring!</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="‹ Orqaga", callback_data="afg_back")
        ]]),
    )
    await callback.answer("📋 Havola tayyorlandi")


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data == "afg_noop")
async def afg_noop(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Allaqachon tanlangan — hech narsa qilmaymiz"""
    await callback.answer("Allaqachon qo'shilgan", show_alert=False)


def _build_responsible_kb(selected_members: list, chosen_resp: set) -> InlineKeyboardMarkup:
    """Masul tanlash klaviaturasi — ko'p tanlov (checkbox style)"""
    buttons = []
    for m in selected_members:
        name = m.display_name or (m.user.full_name if m.user else f"#{m.user_id}")
        icon = "✅" if m.user_id in chosen_resp else "☐"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}",
            callback_data=f"resp:{m.user_id}"
        )])
    done_txt = f"✅ Tayyor ({len(chosen_resp)} masul)" if chosen_resp else "➡️ Masulsiz davom etish"
    buttons.append([InlineKeyboardButton(text=done_txt, callback_data="resp:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(NewTaskStates.waiting_multi_assignee, F.data == "assign_done")
async def process_multi_assignee_done(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot) -> None:
    """Kompaniya ijrochilar tanlovini yakunlash — masul tanlash"""
    data = await state.get_data()
    selected = list(data.get("selected_assignees") or [])
    external = list(data.get("external_assignees") or [])
    ext_ids = [e["id"] for e in external]

    all_assignee_ids = selected + [eid for eid in ext_ids if eid not in selected]

    if not all_assignee_ids:
        await callback.answer("Kamida bitta xodim tanlang", show_alert=True)
        return

    await state.update_data(final_assignees=all_assignee_ids, chosen_responsibles=[])

    if len(all_assignee_ids) == 1:
        await _create_task_final(callback.message, state, user, all_assignee_ids,
                                 responsible_user_ids=[all_assignee_ids[0]], bot=bot)
        await callback.answer("✅ Vazifa yaratildi!")
        return

    # Ko'p kishi — masul tanlash (ko'p tanlov)
    company_id = data.get("company_id")
    group_id   = data.get("group_id")
    async with get_session() as session:
        if group_id and not company_id:
            members = await GroupService.get_members(session, group_id)
        else:
            members = await CompanyService.get_members(session, company_id)

    # Asosiy + tashqi a'zolar uchun _resp_members
    resp_members_raw = []
    for m in members:
        mid = m.user_id if hasattr(m, 'user_id') else (m.user.id if hasattr(m, 'user') else None)
        if mid in all_assignee_ids:
            dname = (getattr(m, 'display_name', None)
                     or (m.user.full_name if hasattr(m, 'user') and m.user else f"#{mid}"))
            resp_members_raw.append({"user_id": mid, "display_name": dname})
    # Tashqi a'zolarni qo'shish
    main_ids = {(m.user_id if hasattr(m, 'user_id') else m.user.id) for m in members}
    for e in external:
        if e["id"] not in main_ids:
            resp_members_raw.append({"user_id": e["id"], "display_name": f"{e['name']} 🔗"})

    await state.update_data(_resp_members=resp_members_raw)
    await state.set_state(NewTaskStates.waiting_responsible)

    class _FakeMember:
        def __init__(self, d): self.user_id = d["user_id"]; self.display_name = d["display_name"]; self.user = None
    fake_members = [_FakeMember(d) for d in resp_members_raw]
    kb = _build_responsible_kb(fake_members, set())
    try:
        await callback.message.edit_text(
            "⭐ <b>Kim masul (responsible)?</b>\n\n"
            "Bir yoki bir nechta kishini belgilang.\n"
            "Masul kishilar vazifani nazorat qiladi va alohida xabar oladi.",
            reply_markup=kb,
        )
    except Exception:
        await callback.message.answer(
            "⭐ <b>Kim masul (responsible)?</b>", reply_markup=kb
        )
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_responsible, F.data.startswith("resp:"))
async def process_responsible_selected(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot) -> None:
    """Masul tanlash — toggle va yakunlash"""
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = data.get("final_assignees") or []
    chosen = set(data.get("chosen_responsibles") or [])
    resp_members_raw = data.get("_resp_members") or []

    if val == "done":
        # Yakunlash
        await _create_task_final(
            callback.message, state, user, selected,
            responsible_user_ids=list(chosen) if chosen else None,
            bot=bot
        )
        await callback.answer("✅ Vazifa yaratildi!")
        return

    # Toggle
    try:
        uid = int(val)
    except ValueError:
        await callback.answer("Xato", show_alert=True)
        return

    if uid in chosen:
        chosen.discard(uid)
    else:
        chosen.add(uid)
    await state.update_data(chosen_responsibles=list(chosen))

    # Klaviaturani yangilash
    class _FakeMember:
        def __init__(self, d): self.user_id = d["user_id"]; self.display_name = d["display_name"]; self.user = None
    fake_members = [_FakeMember(d) for d in resp_members_raw]
    kb = _build_responsible_kb(fake_members, chosen)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(NewTaskStates.waiting_assignee, F.data.startswith("assignee:"))
async def process_assignee(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot) -> None:
    """Ijrochi tanlash va vazifani yaratish (bitta kishi — avtomatik masul)"""
    assignee_id = int(callback.data.split(":")[1])
    await _create_task_final(callback.message, state, user, [assignee_id], responsible_user_id=assignee_id, bot=bot)
    await callback.answer("✅ Vazifa yaratildi!")


async def _create_task_final(
    message: Message, state: FSMContext, user: User,
    assignee_ids: list, bot: Bot = None,
    responsible_user_id: int = None,
    responsible_user_ids: list = None,
) -> None:
    """Yakuniy vazifa yaratish"""
    data = await state.get_data()

    # Ma'lumotlar borligini tekshirish
    if "title" not in data or "priority" not in data:
        await state.clear()
        await message.answer(
            "❗ Xatolik yuz berdi. Iltimos, /newtask orqali qaytadan boshlang.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.fromisoformat(data["deadline"])
        except (ValueError, TypeError):
            pass

    text = "✅ Vazifa yaratildi!"
    try:
        async with get_session() as session:
            task = await TaskService.create_task(
                session=session,
                title=data["title"],
                description=data.get("description"),
                priority=Priority(data["priority"]),
                deadline=deadline,
                creator_id=user.id,
                group_id=data.get("group_id"),
                company_id=data.get("company_id"),
                assignee_ids=assignee_ids,
                responsible_user_id=responsible_user_id,
                responsible_user_ids=responsible_user_ids,
                parent_id=data.get("parent_id"),
            )
            # Fayl biriktirmalarini saqlash
            atts = data.get("attachments") or []
            for a in atts:
                try:
                    session.add(TaskAttachment(
                        task_id=task.id,
                        user_id=user.id,
                        file_type=a.get("file_type", "document"),
                        file_id=a.get("file_id"),
                        file_name=a.get("file_name"),
                        file_size=a.get("file_size"),
                        mime_type=a.get("mime_type"),
                    ))
                except Exception as _e:
                    logger.warning(f"Attachment save xatosi: {_e}")

            await session.commit()

            # Qayta yuklash (barcha relations bilan) — session ichida!
            task = await TaskService.get_task(session, task.id)

            # Matnni session ichida generatsiya qilamiz (lazy load xavfi yo'q)
            if task:
                text = (
                    f"✅ <b>Vazifa muvaffaqiyatli yaratildi!</b>\n\n"
                    f"{format_task_detailed(task)}"
                )

            # Masul ro'yxatini bildirishnoma uchun aniqlaymiz
            resp_ids = responsible_user_ids or (
                [responsible_user_id] if responsible_user_id else []
            )

            if bot and task:
                try:
                    await NotificationService.notify_task_assigned(
                        bot, session, task, assignee_ids,
                        responsible_user_ids=resp_ids,
                    )
                except Exception as e:
                    logger.warning(f"Task notification xatosi: {e}")

                # Guruh chatiga e'lon yuborish
                try:
                    await _notify_group_task_created(bot, session, task, assignee_ids)
                except Exception as e:
                    logger.warning(f"Group task announce xatosi: {e}")

        try:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        except Exception:
            await message.answer(text, reply_markup=back_to_menu_keyboard())

    except Exception as e:
        logger.exception(f"Vazifa yaratishda xatolik: {e}")
        try:
            await message.answer(
                "❗ Vazifa yaratishda xatolik yuz berdi. Qaytadan urinib ko'ring.",
                reply_markup=back_to_menu_keyboard(),
            )
        except Exception:
            pass
    finally:
        await state.clear()


# ===== Vazifalar ro'yxati =====

def _mytasks_ws_keyboard(companies: list) -> InlineKeyboardMarkup:
    """Workspace tanlash klaviaturasi — Hammasi / Shaxsiy / har bir jamoa"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [
        [InlineKeyboardButton(text="🌍 Hammasi",  callback_data="mytasks:ws:all")],
        [InlineKeyboardButton(text="👤 Shaxsiy",  callback_data="mytasks:ws:personal")],
    ]
    for c in companies:
        rows.append([InlineKeyboardButton(
            text=f"🏢 {c['name']}",
            callback_data=f"mytasks:ws:co:{c['id']}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_tasks_for_workspace(
    message, user: User, workspace: str, edit: bool = False
) -> None:
    """Tanlangan workspace bo'yicha vazifalarni ko'rsatish"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    async with get_session() as session:
        from sqlalchemy import select as sa_select
        from database.models import TaskAssignment, Company, CompanyMember

        if workspace == "all":
            tasks = await TaskService.get_user_tasks(session, user.id)
            ws_label = "🌍 Hammasi"
        elif workspace == "personal":
            from sqlalchemy import and_
            from database.models import Task as TaskModel
            result = await session.execute(
                sa_select(TaskModel)
                .join(TaskAssignment, TaskAssignment.task_id == TaskModel.id)
                .where(
                    TaskAssignment.user_id == user.id,
                    TaskModel.company_id.is_(None),
                    TaskModel.group_id.is_(None),
                    TaskModel.status.notin_(["DONE", "CANCELLED", "done", "cancelled"]),
                )
                .order_by(TaskModel.deadline.asc().nullslast(), TaskModel.created_at.desc())
            )
            tasks = list(result.scalars().all())
            ws_label = "👤 Shaxsiy"
        else:
            # company id
            try:
                co_id = int(workspace)
            except ValueError:
                tasks = []
                ws_label = "?"
            else:
                from database.models import Task as TaskModel
                result = await session.execute(
                    sa_select(TaskModel)
                    .join(TaskAssignment, TaskAssignment.task_id == TaskModel.id)
                    .where(
                        TaskAssignment.user_id == user.id,
                        TaskModel.company_id == co_id,
                        TaskModel.status.notin_(["DONE", "CANCELLED", "done", "cancelled"]),
                    )
                    .order_by(TaskModel.deadline.asc().nullslast(), TaskModel.created_at.desc())
                )
                tasks = list(result.scalars().all())
                co = await session.get(Company, co_id)
                ws_label = f"🏢 {co.name}" if co else f"Jamoa #{co_id}"

    # Back tugmasi (workspace tanloviga qaytish)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Workspace tanlash", callback_data="menu:mytasks")]
    ])

    if not tasks:
        text = (
            f"📋 <b>{ws_label}</b>\n\n"
            "✅ Bu bo'limda faol vazifalar yo'q.\n\n"
            "<i>Yangi vazifa: /newtask</i>"
        )
        if edit:
            try:
                await message.edit_text(text, reply_markup=back_kb)
            except Exception:
                await message.answer(text, reply_markup=back_kb)
        else:
            await message.answer(text, reply_markup=back_kb)
        return

    text = f"📋 <b>{ws_label}</b> — {len(tasks)} ta vazifa\n\nVazifani tanlang:"

    # task_list_keyboard + back tugmasi
    from keyboards.inline import task_list_keyboard as tlk
    kb = tlk(tasks)
    # Oxirgi qatorga "Workspace tanlash" tugmasini qo'shamiz
    kb.inline_keyboard.insert(0, [
        InlineKeyboardButton(text="🔙 Workspace tanlash", callback_data="menu:mytasks")
    ])

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(F.text == "📋 Vazifalarim")
async def cmd_my_tasks(event, user: User) -> None:
    """Mening vazifalarim — workspace tanlash"""
    message = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()

    async with get_session() as session:
        from sqlalchemy import select as sa_select
        from database.models import Company, CompanyMember
        rows = await session.execute(
            sa_select(Company)
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user.id)
        )
        companies = [{"id": c.id, "name": c.name} for c in rows.scalars()]

    kb = _mytasks_ws_keyboard(companies)
    text = (
        "📋 <b>Mening vazifalarim</b>\n\n"
        "Qaysi bo'limni ko'rmoqchisiz?"
    )
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:mytasks")
async def cb_mytasks_picker(callback: CallbackQuery, user: User) -> None:
    """Inline menyu va back tugmasidan workspace picker ochish"""
    async with get_session() as session:
        from sqlalchemy import select as sa_select
        from database.models import Company, CompanyMember
        rows = await session.execute(
            sa_select(Company)
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user.id)
        )
        companies = [{"id": c.id, "name": c.name} for c in rows.scalars()]

    kb = _mytasks_ws_keyboard(companies)
    text = "📋 <b>Mening vazifalarim</b>\n\nQaysi bo'limni ko'rmoqchisiz?"
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mytasks:ws:"))
async def cb_mytasks_workspace(callback: CallbackQuery, user: User) -> None:
    """Workspace tanlangandan so'ng vazifalarni ko'rsatish"""
    # mytasks:ws:all | mytasks:ws:personal | mytasks:ws:co:123
    parts = callback.data.split(":")  # ['mytasks','ws','all'] or ['mytasks','ws','co','123']
    if len(parts) == 3:
        workspace = parts[2]          # "all" | "personal"
    else:
        workspace = parts[3]          # company id string

    await _show_tasks_for_workspace(callback.message, user, workspace, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("tasks_page:"))
async def callback_tasks_page(callback: CallbackQuery, user: User) -> None:
    """Sahifa o'zgartirish"""
    page = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        tasks = await TaskService.get_user_tasks(session, user.id)
    
    try:
        await callback.message.edit_reply_markup(
            reply_markup=task_list_keyboard(tasks, page=page)
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("view_task:"))
@router.callback_query(F.data.startswith("task_view:"))
async def callback_task_view(callback: CallbackQuery, user: User) -> None:
    """Vazifa tafsilotlarini ko'rsatish"""
    task_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        task = await TaskService.get_task(session, task_id)
        if not task:
            await callback.answer("❗ Vazifa topilmadi", show_alert=True)
            return

        is_assignee = await TaskService.is_user_assignee(session, user.id, task_id)
        user_role = UserRole.EXECUTOR
        if task.group_id:
            role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
            if role:
                user_role = role
        elif task.company_id:
            from database.models import CompanyRole
            c_role = await CompanyService.is_member(session, task.company_id, user.id)
            if c_role in (CompanyRole.OWNER, CompanyRole.ADMIN):
                user_role = UserRole.ADMIN
            elif task.creator_id == user.id:
                user_role = UserRole.MANAGER
        elif task.creator_id == user.id:
            user_role = UserRole.ADMIN

    await callback.message.edit_text(
        format_task_detailed(task),
        reply_markup=task_actions_keyboard(task, user_role, is_assignee),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_status:"))
async def callback_task_status(callback: CallbackQuery, user: User, bot: Bot) -> None:
    """Vazifa statusini o'zgartirish"""
    parts = callback.data.split(":")
    task_id = int(parts[1])
    new_status = TaskStatus(parts[2])
    
    async with get_session() as session:
        task = await TaskService.get_task(session, task_id)
        if not task:
            await callback.answer("❗ Vazifa topilmadi", show_alert=True)
            return
        
        old_status = task.status
        
        updated_task = await TaskService.update_task_status(
            session, task_id, new_status, user.id
        )
        await session.commit()
        
        if updated_task:
            try:
                await NotificationService.notify_status_changed(
                    bot, session, updated_task,
                    old_status.value, new_status.value,
                    user.full_name,
                )
            except Exception as e:
                logger.warning(f"Status notification xatosi: {e}")

            # Guruh chatiga status o'zgarishi xabari
            try:
                await _notify_group_status_changed(
                    bot, session, updated_task,
                    old_status, new_status, user
                )
            except Exception as e:
                logger.warning(f"Group status notify xatosi: {e}")

            is_assignee = await TaskService.is_user_assignee(session, user.id, task_id)
            user_role = UserRole.EXECUTOR
            if task.group_id:
                role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
                if role:
                    user_role = role
            elif task.creator_id == user.id:
                user_role = UserRole.ADMIN
            
            await callback.message.edit_text(
                format_task_detailed(updated_task),
                reply_markup=task_actions_keyboard(updated_task, user_role, is_assignee),
            )
    
    await callback.answer("✅ Status yangilandi!")


@router.callback_query(F.data.startswith("task_delete:"))
async def callback_task_delete_confirm(callback: CallbackQuery, user: User) -> None:
    """Vazifani o'chirish - tasdiq so'rash"""
    task_id = int(callback.data.split(":")[1])
    
    await callback.message.edit_text(
        "⚠️ <b>Vazifani o'chirishni xohlaysizmi?</b>\n\n"
        "<i>Bu amalni bekor qilib bo'lmaydi!</i>",
        reply_markup=confirm_keyboard("delete_task", task_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:delete_task:"))
async def callback_task_delete_execute(callback: CallbackQuery, user: User) -> None:
    """Vazifani o'chirish - tasdiqlangan"""
    task_id = int(callback.data.split(":")[2])
    
    async with get_session() as session:
        success = await TaskService.delete_task(session, task_id, user.id)
    
    if success:
        await callback.message.edit_text(
            "✅ Vazifa o'chirildi.",
            reply_markup=back_to_menu_keyboard(),
        )
        await callback.answer("Vazifa o'chirildi!")
    else:
        await callback.answer("❗ Xato yuz berdi", show_alert=True)


# ===== Kechikkan va barcha vazifalar =====

@router.callback_query(F.data == "menu:overdue")
async def cmd_overdue(event, user: User) -> None:
    """Kechikkan vazifalar"""
    if isinstance(event, CallbackQuery):
        message = event.message
        edit = True
        await event.answer()
    else:
        message = event
        edit = False
    
    async with get_session() as session:
        all_tasks = await TaskService.get_user_tasks(session, user.id, include_completed=True)
        overdue = [t for t in all_tasks if t.status == TaskStatus.OVERDUE]
    
    if not overdue:
        text = "🎉 <b>Ajoyib!</b>\n\nSizda kechikkan vazifalar yo'q!"
        if edit:
            await message.edit_text(text, reply_markup=back_to_menu_keyboard())
        else:
            await message.answer(text, reply_markup=back_to_menu_keyboard())
        return
    
    text = f"⏰ <b>Kechikkan vazifalar</b> ({len(overdue)} ta)\n\n"
    text += "<i>Darhol ko'rib chiqishingiz kerak!</i>"
    
    if edit:
        await message.edit_text(text, reply_markup=task_list_keyboard(overdue))
    else:
        await message.answer(text, reply_markup=task_list_keyboard(overdue))


@router.message(Command("alltasks"))
async def cmd_all_tasks(message: Message, user: User) -> None:
    """Barcha vazifalar (guruhda yoki shaxsiy)"""
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if not group:
                await message.answer("❗ Bu guruh ro'yxatdan o'tmagan. /start yuboring.")
                return
            
            role = await TaskService.get_user_role_in_group(session, user.id, group.id)
            if role not in (UserRole.ADMIN, UserRole.MANAGER):
                await message.answer("🚫 Bu buyruq faqat admin/menejer uchun.")
                return
            
            tasks = await TaskService.get_group_tasks(session, group.id)
    else:
        async with get_session() as session:
            tasks = await TaskService.get_user_tasks(
                session, user.id, include_completed=True
            )
    
    if not tasks:
        await message.answer("📋 Vazifalar yo'q.", reply_markup=back_to_menu_keyboard())
        return
    
    await message.answer(
        f"📋 <b>Barcha vazifalar</b> ({len(tasks)} ta)",
        reply_markup=task_list_keyboard(tasks),
    )


# ═══════════════════════════════════════════════════════════════
#  GURUH NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════

async def _get_group_telegram_id(session, group_id: int) -> int | None:
    """Guruh DB id → Telegram chat id"""
    from database.models import Group
    from sqlalchemy import select as sa_select
    res = await session.execute(sa_select(Group).where(Group.id == group_id))
    g = res.scalar_one_or_none()
    return g.telegram_group_id if g else None


async def _resolve_tg_chat_id(session, task) -> int | None:
    """
    Vazifaning telegram guruh chat ID sini aniqlash.
    1. task.group_id → Group.telegram_group_id
    2. task.company_id → kompaniyaning birinchi aktiv guruh telegram_group_id
    """
    from database.models import Group
    from sqlalchemy import select as sa_select

    if task.group_id:
        tg_id = await _get_group_telegram_id(session, task.group_id)
        logger.info(f"Task {task.id}: group_id={task.group_id}, telegram_group_id={tg_id}")
        if tg_id:
            return tg_id

    if task.company_id:
        res = await session.execute(
            sa_select(Group).where(
                Group.company_id == task.company_id,
                Group.telegram_group_id.isnot(None),
                Group.is_active == True,
            ).limit(1)
        )
        grp = res.scalar_one_or_none()
        tg_id = grp.telegram_group_id if grp else None
        logger.info(f"Task {task.id}: company_id={task.company_id} → group telegram_group_id={tg_id}")
        return tg_id

    logger.info(f"Task {task.id}: group_id=None, company_id=None — guruh topilmadi")
    return None


async def _notify_group_task_created(bot: Bot, session, task, assignee_ids: list) -> None:
    """Guruh chatiga yangi task e'lon yuborish"""
    tg_chat_id = await _resolve_tg_chat_id(session, task)
    if not tg_chat_id:
        logger.info(f"Task {task.id} uchun guruh chat ID topilmadi — guruh xabari yuborilmadi")
        return

    # Ijrochilar ismlarini olamiz
    from database.models import User as UserModel
    names = []
    for uid in assignee_ids:
        u = await session.get(UserModel, uid)
        if u:
            mention = f"@{u.username}" if u.username else u.full_name
            names.append(mention)

    priority_em = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}.get(
        task.priority.value if hasattr(task.priority, "value") else str(task.priority), "📌"
    )

    deadline_txt = ""
    if task.deadline:
        deadline_txt = f"\n⏰ Deadline: <b>{task.deadline.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}</b>"

    assignees_txt = ", ".join(names) if names else "—"

    text = (
        f"📋 <b>Yangi vazifa yaratildi!</b>\n\n"
        f"📌 <b>{task.title}</b>  <code>#{task.id}</code>\n"
        f"{priority_em} Muhimlik: {task.priority.value if hasattr(task.priority, 'value') else task.priority}\n"
        f"👤 Ijrochi(lar): {assignees_txt}"
        f"{deadline_txt}\n\n"
        f"🔹 Vazifani ko'rish: /task_{task.id}"
    )
    if task.description:
        text += f"\n\n📝 {task.description[:200]}"

    try:
        await bot.send_message(tg_chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Guruhga e'lon yuborishda xato {tg_chat_id}: {e}")


async def _notify_group_status_changed(
    bot: Bot, session, task, old_status: TaskStatus, new_status: TaskStatus, changer: User
) -> None:
    """Guruh chatiga status o'zgarishi xabari"""
    tg_chat_id = await _resolve_tg_chat_id(session, task)
    if not tg_chat_id:
        return

    STATUS_EM = {
        TaskStatus.NEW:         ("🆕", "Yangi"),
        TaskStatus.IN_PROGRESS: ("⚙️", "Jarayonda"),
        TaskStatus.REVIEW:      ("🔍", "Ko'rib chiqilmoqda"),
        TaskStatus.DONE:        ("✅", "Bajarildi"),
        TaskStatus.OVERDUE:     ("⏰", "Kechikdi"),
        TaskStatus.CANCELLED:   ("🚫", "Bekor qilindi"),
    }
    old_em, old_txt = STATUS_EM.get(old_status, ("❓", str(old_status)))
    new_em, new_txt = STATUS_EM.get(new_status, ("❓", str(new_status)))

    changer_mention = f"@{changer.username}" if changer.username else changer.full_name

    text = (
        f"{new_em} <b>Vazifa holati o'zgardi!</b>\n\n"
        f"📌 <b>{task.title}</b>  <code>#{task.id}</code>\n"
        f"{old_em} {old_txt}  →  {new_em} <b>{new_txt}</b>\n"
        f"👤 O'zgartirdi: {changer_mention}"
    )

    # Bajarildi bo'lsa — tabriklash
    if new_status == TaskStatus.DONE:
        text += "\n\n🎉 <b>Ajoyib! Vazifa muvaffaqiyatli yakunlandi!</b>"

    try:
        await bot.send_message(tg_chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Guruhga status notify xatosi {tg_chat_id}: {e}")


# ═══════════════════════════════════════════════════════════════
#  GURUHDA TO'G'RIDAN-TO'G'RI BUYRUQLAR
# ═══════════════════════════════════════════════════════════════

@router.message(Command("task"))
async def cmd_task_by_id(message: Message, user: User) -> None:
    """/task_42 yoki /task 42 — vazifa tafsilotlari (guruhda ham ishlaydi)"""
    # /task_42 yoki /task 42 formatini qo'llab-quvvatlash
    text_part = (message.text or "").replace("/task_", "/task ").strip()
    parts = text_part.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("ℹ️ Foydalanish: <code>/task 42</code>")
        return
    try:
        task_id = int(parts[1].strip())
    except ValueError:
        await message.answer("❗ task_id raqam bo'lishi kerak.")
        return

    async with get_session() as session:
        task = await TaskService.get_task(session, task_id)
        if not task:
            await message.answer("❗ Vazifa topilmadi.")
            return

        is_assignee = await TaskService.is_user_assignee(session, user.id, task_id)
        user_role = UserRole.EXECUTOR
        if task.group_id:
            role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
            if role:
                user_role = role
        elif task.creator_id == user.id:
            user_role = UserRole.ADMIN

    await message.answer(
        format_task_detailed(task),
        reply_markup=task_actions_keyboard(task, user_role, is_assignee),
    )


@router.message(Command("newtask"))
async def cmd_newtask_group(message: Message, state: FSMContext, user: User) -> None:
    """/newtask guruhda va shaxsiy chatda ham ishlaydi"""
    await cmd_new_task(message, state, user)


@router.message(Command("mytasks"))
async def cmd_mytasks_group(message: Message, user: User) -> None:
    """/mytasks guruhda: faqat mening o'sha guruhdagi tasklarim"""
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if not group:
                await message.answer("❗ Bu guruh ro'yxatdan o'tmagan. /start yuboring.")
                return
            from sqlalchemy import select as sa_select
            from database.models import Task as TaskModel, TaskAssignment
            result = await session.execute(
                sa_select(TaskModel)
                .join(TaskAssignment, TaskAssignment.task_id == TaskModel.id)
                .where(
                    TaskAssignment.user_id == user.id,
                    TaskModel.group_id == group.id,
                    TaskModel.status.notin_(["DONE", "CANCELLED", "done", "cancelled"]),
                )
                .order_by(TaskModel.deadline.asc().nullslast(), TaskModel.created_at.desc())
            )
            tasks = list(result.scalars().all())

        if not tasks:
            await message.answer("✅ Bu guruhda sizga biriktirilgan faol vazifa yo'q.")
            return
        await message.answer(
            f"📋 <b>Mening vazifalarim ({group.name})</b> — {len(tasks)} ta",
            reply_markup=task_list_keyboard(tasks),
        )
    else:
        await cmd_my_tasks(message, user)


@router.message(Command("overdue"))
async def cmd_overdue_group(message: Message, user: User) -> None:
    """/overdue guruhda: guruhdagi kechikkan vazifalar"""
    if message.chat.type in ("group", "supergroup"):
        async with get_session() as session:
            group = await GroupService.get_group_by_telegram_id(session, message.chat.id)
            if not group:
                await message.answer("❗ Bu guruh ro'yxatdan o'tmagan.")
                return
            tasks = await TaskService.get_group_tasks(session, group.id, status=TaskStatus.OVERDUE)

        if not tasks:
            await message.answer("🎉 Bu guruhda kechikkan vazifalar yo'q!")
            return
        await message.answer(
            f"⏰ <b>Kechikkan vazifalar ({group.name})</b> — {len(tasks)} ta",
            reply_markup=task_list_keyboard(tasks),
        )
    else:
        await cmd_overdue(message, user)


@router.message(F.text.regexp(r"^/task_(\d+)$"))
async def cmd_view_task_by_id(message: Message, user: User) -> None:
    """/task_123 buyrug'i orqali vazifa ko'rish"""
    try:
        task_id = int(message.text.split("_")[1])
    except (ValueError, IndexError):
        await message.answer("❗ Noto'g'ri format.")
        return
    
    async with get_session() as session:
        task = await TaskService.get_task(session, task_id)
        if not task:
            await message.answer("❗ Vazifa topilmadi.")
            return
        
        is_assignee = await TaskService.is_user_assignee(session, user.id, task_id)
        
        if not is_assignee and task.creator_id != user.id:
            if task.group_id:
                role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
                if not role:
                    await message.answer("🚫 Bu vazifani ko'rish uchun ruxsatingiz yo'q.")
                    return
            else:
                await message.answer("🚫 Ruxsat yo'q.")
                return
        
        user_role = UserRole.EXECUTOR
        if task.group_id:
            role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
            if role:
                user_role = role
        elif task.creator_id == user.id:
            user_role = UserRole.ADMIN

    await message.answer(
        format_task_detailed(task),
        reply_markup=task_actions_keyboard(task, user_role, is_assignee),
    )


# ──────────────────────────────────────────────────────────────────────────────
# SUB-TASK (ICHKI VAZIFA) YARATISH — to'liq task yaratish oqimi bilan
# ──────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("subtask_add:"))
async def callback_subtask_add(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    """Sub-task turi tanlash (Odiy task yoki Ketma-ketlik)"""
    task_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        task = await TaskService.get_task(session, task_id, load_relations=False)
        if not task:
            await callback.answer("❗ Vazifa topilmadi", show_alert=True)
            return
        # Guruh/kompaniya a'zosi yoki yaratuvchi bo'lsa ruxsat
        can_add = task.creator_id == user.id
        if not can_add and task.group_id:
            role = await TaskService.get_user_role_in_group(session, user.id, task.group_id)
            from database.models import UserRole
            can_add = role in (UserRole.ADMIN, UserRole.MANAGER)
        if not can_add and task.company_id:
            from services.company_service import CompanyService as _CS
            role = await _CS.is_member(session, task.company_id, user.id)
            from database.models import CompanyRole
            can_add = role in (CompanyRole.OWNER, CompanyRole.ADMIN, CompanyRole.MANAGER)
        if not can_add:
            await callback.answer("🚫 Sub-task qo'shish huquqi yo'q", show_alert=True)
            return

        parent_company_id = task.company_id
        parent_group_id   = task.group_id

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Odiy sub-task", callback_data=f"subtask_type:regular:{task_id}")],
        [InlineKeyboardButton(text="🔗 Ketma-ketlik", callback_data=f"subtask_type:workflow:{task_id}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")],
    ])
    await callback.message.answer(
        f"📂 <b>Sub-task qo'shish</b>\n"
        f"🔗 Ota-vazifa: #{task_id} — <i>{task.title[:50]}</i>\n\n"
        "Qanday sub-task yaratmoqchisiz?",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subtask_type:"))
async def callback_subtask_type(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot) -> None:
    """Sub-task turini tanlagandan keyin to'liq task yaratish oqimini boshlash"""
    parts = callback.data.split(":")
    sub_type  = parts[1]   # 'regular' | 'workflow'
    task_id   = int(parts[2])

    async with get_session() as session:
        task = await TaskService.get_task(session, task_id, load_relations=False)
        if not task:
            await callback.answer("❗ Vazifa topilmadi", show_alert=True)
            return
        parent_company_id = task.company_id
        parent_group_id   = task.group_id
        parent_title      = task.title

    if sub_type == "workflow":
        # Workflow sub-task — workflow FSM ni ishlatamiz, parent_id ni saqlaymiz
        from handlers.workflow import WorkflowStates
        await state.clear()
        await state.set_state(WorkflowStates.waiting_title)
        await state.update_data(
            steps=[],
            parent_id=task_id,
            company_id=parent_company_id,
            group_id=parent_group_id,
        )
        text = (
            f"🔗 <b>Ketma-ketlik sub-task</b>\n"
            f"🔗 Ota-vazifa: #{task_id} — <i>{parent_title[:50]}</i>\n\n"
            "Vazifa nomini kiriting:"
        )
        try:
            await callback.message.edit_text(text, reply_markup=cancel_keyboard())
        except Exception:
            await callback.message.answer(text, reply_markup=cancel_keyboard())
        await callback.answer()
        return

    # Oddiy sub-task — mavjud task creation FSM ni ishlatamiz
    await state.clear()
    await state.set_state(NewTaskStates.waiting_title)
    # Ota-vazifaning workspace ma'lumotlarini FSM ga saqlaymiz
    # (workspace selection bosqichi o'tkazib yuboriladi)
    await state.update_data(
        parent_id=task_id,
        company_id=parent_company_id,
        group_id=parent_group_id,
    )
    text = (
        f"📋 <b>Odiy sub-task yaratish</b>\n"
        f"🔗 Ota-vazifa: #{task_id} — <i>{parent_title[:50]}</i>\n\n"
        "1/5 qadam: Sub-task <b>nomini</b> kiriting:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=cancel_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("subtask_list:"))
async def callback_subtask_list(callback: CallbackQuery, user: User) -> None:
    """Sub-task ro'yxatini ko'rsatish"""
    task_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        from sqlalchemy import select as _sel
        from database.models import Task as _Task
        result = await session.execute(
            _sel(_Task).where(_Task.parent_id == task_id)
        )
        subtasks = list(result.scalars().all())

    if not subtasks:
        await callback.answer("Hali sub-tasklar yo'q", show_alert=True)
        return

    STATUS_EMOJI_MAP = {"new": "🆕", "in_progress": "⚙️", "done": "✅",
                        "overdue": "⏰", "review": "🔍", "cancelled": "🚫"}
    lines = [f"📂 <b>#{task_id} — Sub-tasklar:</b>\n"]
    for st in subtasks:
        em = STATUS_EMOJI_MAP.get(st.status.value if hasattr(st.status, 'value') else str(st.status), "•")
        lines.append(f"{em} /task_{st.id} — {st.title[:60]}")

    await callback.message.answer("\n".join(lines))
    await callback.answer()
