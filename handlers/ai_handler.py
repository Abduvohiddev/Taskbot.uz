"""
AI Handler - ovozli xabar va matn orqali AI bilan ishlash
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database.db import get_session
from database.models import User, Task, TaskStatus, Priority, TaskAssignment, TaskHistory
from services.ai_service import AIService
from services.notification_service import NotificationService

router = Router()
logger = logging.getLogger(__name__)

PRIORITY_MAP = {
    "low": Priority.LOW,
    "medium": Priority.MEDIUM,
    "high": Priority.HIGH,
    "urgent": Priority.URGENT,
}

PRIORITY_NAME = {"low": "🟢 Past", "medium": "🟡 O'rta", "high": "🟠 Yuqori", "urgent": "🔴 Muhim"}

# Tasdiq kutayotgan vazifalar (xotirada)
# token -> {"user_id":..., "title":..., "description":..., "priority":..., "deadline": datetime}
_PENDING_PROPOSALS: dict = {}

# Foydalanuvchi suhbat tarixi (xotirada)
# user_id -> list of {"role": "user"|"assistant", "content": str}
_USER_HISTORY: dict = {}
_HISTORY_MAX = 12  # oxirgi 6 ta turn

def _push_history(user_id: int, role: str, content: str) -> None:
    h = _USER_HISTORY.setdefault(user_id, [])
    h.append({"role": role, "content": content[:1500]})
    if len(h) > _HISTORY_MAX:
        del h[: len(h) - _HISTORY_MAX]

def _clear_history(user_id: int) -> None:
    _USER_HISTORY.pop(user_id, None)


@router.message(Command("ai"))
@router.message(F.text.in_({"🤖 AI Yordamchi", "🤖 AI Помощник", "🤖 AI Assistant"}))
async def cmd_ai(message: Message) -> None:
    await message.answer(
        "🤖 <b>AI Yordamchi</b>\n\n"
        "Menga o'zbek tilida yozing yoki ovozli xabar yuboring:\n\n"
        "💬 <i>Masalan:</i>\n"
        "• «Ertaga soat 5 ga hisobot tayyorla» — vazifa yaratadi\n"
        "• «Bugungi vazifalarim» — ro'yxat ko'rsatadi\n"
        "• «Statistikam» — hisobot ko'rsatadi\n"
        "• Yoki istalgan savol bering 🎤"
    )


@router.message(F.voice)
async def handle_voice(message: Message, user: User, bot: Bot) -> None:
    """Ovozli xabarni qayta ishlash"""
    wait_msg = await message.answer("🎤 Ovoz tahlil qilinmoqda...")

    try:
        # Ovoz faylini yuklab olish
        voice = message.voice
        file = await bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await bot.download_file(file.file_path, tmp_path)

        # Matnga aylantirish
        text = await AIService.transcribe_voice(tmp_path)
        os.unlink(tmp_path)

        if not text:
            await wait_msg.edit_text("❗ Ovozni tanib bo'lmadi. Qaytadan urining.")
            return

        await wait_msg.edit_text(f"🗣 <i>«{text}»</i>\n\n⏳ AI tahlil qilmoqda...")
        await _process_ai_response(message, user, text)

    except Exception as e:
        logger.error(f"Voice handler xatosi: {e}")
        await wait_msg.edit_text("❗ Xatolik yuz berdi.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_ai(message: Message, user: User) -> None:
    """Oddiy matn xabarini AI orqali qayta ishlash"""
    # Faqat shaxsiy chat da ishlaydi
    if message.chat.type != "private":
        return

    # Qisqa xabarlarni o'tkazib yuborish (navigatsiya tugmalari va h.k.)
    if len(message.text) < 3:
        return

    await _process_ai_response(message, user, message.text)


async def _process_ai_response(message: Message, user: User, text: str) -> None:
    """AI javobini qayta ishlash va bajarish (suhbat tarixi bilan)"""
    history = list(_USER_HISTORY.get(user.id, []))
    result = await AIService.process_message(text, user.full_name, history=history)
    action = result.get("action", "reply")
    logger.info(f"[AI BOT] user={user.id} text={text!r} → action={action} result={result}")

    # Tarixga qo'shamiz
    _push_history(user.id, "user", text)

    if action == "ask_more":
        ask_text = result.get("text", "Yana ma'lumot kerak.")
        # Draft ni ham tarixga qo'yamiz, AI eslab qolsin
        draft = result.get("draft") or {}
        draft_summary = (
            f"[Mening hozirgi vazifa loyiham: nom={draft.get('title')}, "
            f"tavsif={draft.get('description')}, muhimlik={draft.get('priority')}, "
            f"deadline={draft.get('deadline')}] {ask_text}"
        )
        _push_history(user.id, "assistant", draft_summary)
        await message.answer(f"🤖 {ask_text}")

    elif action in ("propose_task", "create_task"):
        await _propose_task_from_ai(message, user, result)
        _push_history(user.id, "assistant", "[Vazifa taklifi tasdiqlash uchun yuborildi]")

    elif action == "list_tasks":
        _push_history(user.id, "assistant", "[Vazifalar ro'yxati ko'rsatildi]")
        await _show_tasks(message, user)

    elif action == "show_stats":
        _push_history(user.id, "assistant", "[Statistika ko'rsatildi]")
        await _show_stats(message, user)

    else:
        reply_text = result.get("text", "Tushunmadim, qaytadan ayting.")
        _push_history(user.id, "assistant", reply_text[:500])
        await message.answer(f"🤖 {reply_text}")


async def _propose_task_from_ai(message: Message, user: User, data: dict) -> None:
    """AI taklif qilgan vazifani foydalanuvchiga tasdiqlash uchun ko'rsatadi.
    Avval workspace tanlash so'raladi, keyin yakuniy tasdiq."""
    title = (data.get("title") or "").strip()
    desc = (data.get("description") or "").strip()
    prio_str = data.get("priority") or "medium"
    dl_str = data.get("deadline")

    # Majburiy maydonlar
    missing = []
    if not title: missing.append("📌 NOMI")
    if not desc: missing.append("📝 TAVSIF")
    if not dl_str: missing.append("⏰ DEADLINE")

    if missing:
        await message.answer(
            "❗ Vazifa yaratish uchun yana shu ma'lumotlar kerak:\n\n"
            + "\n".join(f"• {m}" for m in missing)
            + "\n\nIltimos, ularni qo'shing va qaytadan yozing."
        )
        return

    # Deadline parse — VAQT MAJBURIY
    deadline = None
    try:
        deadline = datetime.strptime(dl_str, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        deadline = None

    if not deadline:
        await message.answer(
            "⏰ <b>Deadline VAQTI ham kerak!</b>\n\n"
            "Iltimos, soatni aniq yozing — masalan:\n"
            "• <code>ertaga 15:00</code>\n"
            "• <code>25.04.2026 18:00</code>\n"
            "• <code>bugun 20:30</code>"
        )
        return

    # Vaqt 00:00 bo'lsa ham — ehtimol AI o'zi qo'ygan, foydalanuvchidan tasdiq so'raymiz
    if deadline.hour == 0 and deadline.minute == 0:
        await message.answer(
            "⏰ Deadline vaqti aniqlanmadi (faqat sana).\n"
            f"Hozir: <b>{deadline.strftime('%d.%m.%Y')} 00:00</b>\n\n"
            "Iltimos, vaqtni ham yozing — masalan: <code>15:00</code> yoki <code>18:30</code>"
        )
        return

    # Foydalanuvchining workspaces ro'yxatini olamiz
    from sqlalchemy import select
    from database.models import Company, CompanyMember
    async with get_session() as session:
        cm_res = await session.execute(
            select(Company).join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user.id)
        )
        companies = list(cm_res.scalars().unique().all())

    # Token saqlaymiz (workspace hali tanlanmagan)
    token = uuid.uuid4().hex[:16]
    _PENDING_PROPOSALS[token] = {
        "user_id": user.id,
        "title": title,
        "description": desc,
        "priority": prio_str,
        "deadline": deadline,
        "company_id": None,
    }

    pn = PRIORITY_NAME.get(prio_str, "🟡 O'rta")

    # Agar foydalanuvchining kompaniyalari yo'q bo'lsa — to'g'ridan-to'g'ri shaxsiy
    if not companies:
        _PENDING_PROPOSALS[token]["company_id"] = None  # personal
        await _show_final_proposal(message, token)
        return

    # Workspace tanlash so'raladi
    text = (
        "📋 <b>Vazifa tafsilotlari yig'ildi:</b>\n\n"
        f"📌 <b>Nomi:</b> {title}\n"
        f"📝 <b>Tavsif:</b> {desc}\n"
        f"⚡ <b>Muhimlik:</b> {pn}\n"
        f"⏰ <b>Deadline:</b> {deadline.strftime('%d.%m.%Y %H:%M')}\n\n"
        "📁 <b>Qaysi workspace ga qo'shaman?</b>"
    )

    rows = [[InlineKeyboardButton(text="👤 Shaxsiy", callback_data=f"aiws:{token}:p")]]
    for c in companies[:8]:
        rows.append([InlineKeyboardButton(text=f"🏢 {c.name}", callback_data=f"aiws:{token}:{c.id}")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"aino:{token}")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_final_proposal(message_or_call, token: str) -> None:
    """Workspace tanlangach yakuniy tasdiq kartasi."""
    proposal = _PENDING_PROPOSALS.get(token)
    if not proposal:
        return
    pn = PRIORITY_NAME.get(proposal["priority"], "🟡 O'rta")

    ws_label = "👤 Shaxsiy"
    if proposal.get("company_id"):
        from sqlalchemy import select
        from database.models import Company
        async with get_session() as session:
            co = await session.execute(select(Company).where(Company.id == proposal["company_id"]))
            co_obj = co.scalar_one_or_none()
            if co_obj:
                ws_label = f"🏢 {co_obj.name}"

    text = (
        "📋 <b>Vazifa tafsilotlari</b>\n"
        "<i>(tasdiqlashingiz uchun)</i>\n\n"
        f"📌 <b>Nomi:</b> {proposal['title']}\n"
        f"📝 <b>Tavsif:</b> {proposal['description']}\n"
        f"⚡ <b>Muhimlik:</b> {pn}\n"
        f"⏰ <b>Deadline:</b> {proposal['deadline'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📁 <b>Workspace:</b> {ws_label}\n\n"
        "Hammasi to'g'rimi?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash va yaratish", callback_data=f"aiok:{token}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"aino:{token}")],
    ])

    if hasattr(message_or_call, "edit_text"):
        try:
            await message_or_call.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await message_or_call.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("aiws:"))
async def cb_ai_workspace(call: CallbackQuery, user: User) -> None:
    """Foydalanuvchi workspace tanladi."""
    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Noto'g'ri ma'lumot.", show_alert=True)
        return
    token, ws = parts[1], parts[2]
    proposal = _PENDING_PROPOSALS.get(token)
    if not proposal:
        await call.answer("Bu taklif eskirgan.", show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        return
    if proposal["user_id"] != user.id:
        await call.answer("Bu sizniki emas.", show_alert=True)
        return

    if ws == "p":
        proposal["company_id"] = None
    else:
        try:
            proposal["company_id"] = int(ws)
        except ValueError:
            proposal["company_id"] = None

    await call.answer("Workspace tanlandi")
    await _show_final_proposal(call.message, token)


@router.callback_query(F.data.startswith("aiok:"))
async def cb_ai_confirm(call: CallbackQuery, user: User) -> None:
    """Foydalanuvchi tasdiqladi — vazifani yaratamiz."""
    token = call.data.split(":", 1)[1]
    proposal = _PENDING_PROPOSALS.pop(token, None)
    if not proposal:
        await call.answer("Bu taklif eskirgan, qayta urining.", show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        return
    if proposal["user_id"] != user.id:
        await call.answer("Bu sizniki emas.", show_alert=True)
        return

    async with get_session() as session:
        task = Task(
            title=proposal["title"],
            description=proposal["description"],
            priority=PRIORITY_MAP.get(proposal["priority"], Priority.MEDIUM),
            deadline=proposal["deadline"],
            creator_id=user.id,
            company_id=proposal.get("company_id"),
            status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()
        session.add(TaskAssignment(task_id=task.id, user_id=user.id))
        session.add(TaskHistory(
            task_id=task.id, user_id=user.id, action="created",
            new_value={"title": proposal["title"], "source": "ai_confirmed"},
        ))
        task_id = task.id
        await session.commit()

    pn = PRIORITY_NAME.get(proposal["priority"], "🟡 O'rta")
    ws_label = "👤 Shaxsiy"
    if proposal.get("company_id"):
        from sqlalchemy import select
        from database.models import Company
        async with get_session() as session:
            co = await session.execute(select(Company).where(Company.id == proposal["company_id"]))
            co_obj = co.scalar_one_or_none()
            if co_obj:
                ws_label = f"🏢 {co_obj.name}"

    new_text = (
        "✨ <b>Vazifa yaratildi!</b>\n\n"
        f"🆔 <b>ID:</b> #{task_id}\n"
        f"📌 <b>Nomi:</b> {proposal['title']}\n"
        f"📝 <b>Tavsif:</b> {proposal['description']}\n"
        f"⚡ <b>Muhimlik:</b> {pn}\n"
        f"⏰ <b>Deadline:</b> {proposal['deadline'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📁 <b>Workspace:</b> {ws_label}\n"
        f"📊 <b>Status:</b> 🆕 Yangi\n\n"
        f"Batafsil: /task_{task_id}"
    )
    try:
        await call.message.edit_text(new_text)
    except Exception:
        await call.message.answer(new_text)
    _clear_history(user.id)
    await call.answer("✅ Vazifa yaratildi!")


@router.callback_query(F.data.startswith("aino:"))
async def cb_ai_cancel(call: CallbackQuery, user: User) -> None:
    """Foydalanuvchi bekor qildi."""
    token = call.data.split(":", 1)[1]
    proposal = _PENDING_PROPOSALS.pop(token, None)
    if proposal and proposal["user_id"] != user.id:
        await call.answer("Bu sizniki emas.", show_alert=True)
        return
    try:
        await call.message.edit_text("❌ <b>Vazifa yaratish bekor qilindi.</b>")
    except Exception:
        await call.message.answer("❌ Bekor qilindi.")
    _clear_history(user.id)
    await call.answer("Bekor qilindi")


async def _show_tasks(message: Message, user: User) -> None:
    """Foydalanuvchi vazifalarini ko'rsatish"""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with get_session() as session:
        from sqlalchemy import and_
        result = await session.execute(
            select(Task)
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                and_(
                    TaskAssignment.user_id == user.id,
                    Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                )
            )
            .order_by(Task.deadline.asc().nullslast())
            .limit(10)
        )
        tasks = result.scalars().all()

    if not tasks:
        await message.answer("📋 Hozircha faol vazifalar yo'q.")
        return

    status_emoji = {
        "NEW": "🆕", "IN_PROGRESS": "⚙️", "REVIEW": "🔍",
        "OVERDUE": "⏰", "DONE": "✅",
    }
    lines = ["📋 <b>Faol vazifalaringiz:</b>\n"]
    for t in tasks:
        st = t.status.name if hasattr(t.status, 'name') else str(t.status)
        emoji = status_emoji.get(st, "•")
        dl = f" | ⏰ {t.deadline.strftime('%d.%m')}" if t.deadline else ""
        lines.append(f"{emoji} /task_{t.id} — {t.title[:40]}{dl}")

    await message.answer("\n".join(lines))


async def _show_stats(message: Message, user: User) -> None:
    """Statistikani ko'rsatish"""
    from sqlalchemy import select, func, and_
    async with get_session() as session:
        result = await session.execute(
            select(Task.status, func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(TaskAssignment.user_id == user.id)
            .group_by(Task.status)
        )
        counts = {(r[0].name if hasattr(r[0], 'name') else r[0]): r[1] for r in result.all()}

    total = sum(counts.values())
    done = counts.get("DONE", 0)
    rate = round(done / total * 100) if total else 0

    await message.answer(
        f"📊 <b>Sizning statistikangiz:</b>\n\n"
        f"📌 Jami: <b>{total}</b>\n"
        f"✅ Bajarildi: <b>{done}</b>\n"
        f"⚙️ Jarayonda: <b>{counts.get('IN_PROGRESS', 0)}</b>\n"
        f"🆕 Yangi: <b>{counts.get('NEW', 0)}</b>\n"
        f"⏰ Kechikdi: <b>{counts.get('OVERDUE', 0)}</b>\n\n"
        f"🏆 Bajarilish: <b>{rate}%</b>"
    )
