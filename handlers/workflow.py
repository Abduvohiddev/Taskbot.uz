"""
Workflow handler — ketma-ket vazifa yaratish (multi-step approval).

Yangiliklar:
  - /wf <id>          → Workflow detail ko'rish
  - wf:view:<id>      → Inline tugma orqali detail
  - wf:subtask:<id>   → Subtask qo'shish
  - /workflows        → Ro'yxatda har bir element bosiladigan
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.db import get_session
from database.models import (
    User, Task, TaskStep, TaskStatus, Priority,
    Company, CompanyMember, TaskAssignment,
    TaskStepComment, TaskStepAttachment, TaskComment,
)
from services.task_service import TaskService
from services.company_service import CompanyService
from config import settings

router = Router()
logger = logging.getLogger(__name__)


def activate_step(step, now: datetime | None = None) -> None:
    """Qadamni AKTIV holatga o'tkazadi.

    NISBIY MUDDAT: agar qadamda `duration_days` bo'lsa, deadline aynan SHU PAYTDAN
    qayta hisoblanadi (aktivlashgan vaqt + N kun). Shu tufayli oldingi qadam
    kechikkan bo'lsa ham, bu odam o'zining to'liq muddatini oladi — kaskad kechikish
    keyingi odamlarga o'tmaydi.
    """
    if now is None:
        now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
    step.status = "active"
    step.started_at = now
    step.completed_at = None
    d = getattr(step, "duration_days", None)
    if d:
        try:
            step.deadline = now + timedelta(days=int(d))
        except (ValueError, TypeError):
            pass
    # Yangi muddat uchun eslatma flaglarini tozalaymiz
    for _f in ("step_warned_morning", "step_warned_3h", "step_warned_2h",
               "step_warned_1h", "step_warned_exact"):
        if hasattr(step, _f):
            setattr(step, _f, False)


# ─── States ──────────────────────────────────────────────────────────────────

class WorkflowStates(StatesGroup):
    waiting_title         = State()
    waiting_description   = State()
    waiting_step_title    = State()
    waiting_step_assignee = State()
    waiting_step_deadline = State()
    waiting_more_steps    = State()
    waiting_observers     = State()
    waiting_workspace     = State()
    waiting_confirm       = State()
    waiting_wf_comment    = State()


class StepCompleteStates(StatesGroup):
    """Qadamni tugatish FSM"""
    choosing_status = State()
    waiting_comment = State()
    waiting_files   = State()


class SubtaskStates(StatesGroup):
    """Subtask qo'shish FSM"""
    waiting_title    = State()
    waiting_assignee = State()


# ─── Shared keyboards ────────────────────────────────────────────────────────

def _cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wf:cancel")]
    ])


def _more_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yana qadam qo'shish", callback_data="wf:add_more")],
        [InlineKeyboardButton(text="✅ Tugallash va saqlash",  callback_data="wf:finish")],
        [InlineKeyboardButton(text="❌ Bekor qilish",          callback_data="wf:cancel")],
    ])


def _step_status_kb(task_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi",              callback_data=f"sc:done:{task_id}")],
        [InlineKeyboardButton(text="⏸ To'xtatildi (blocked)",  callback_data=f"sc:blocked:{task_id}")],
        [InlineKeyboardButton(text="❌ Bekor qilish",           callback_data="sc:cancel")],
    ])


def _step_files_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tayyor — saqlash", callback_data="sc:finish"),
         InlineKeyboardButton(text="⏭ Faylsiz",          callback_data="sc:nofiles")],
        [InlineKeyboardButton(text="❌ Bekor qilish",     callback_data="sc:cancel")],
    ])


# ─── Workspace helpers ───────────────────────────────────────────────────────

async def _get_user_workspaces(user_id: int) -> List[dict]:
    items: List[dict] = [{"id": "personal", "name": "👤 Shaxsiy", "company_id": None}]
    async with get_session() as session:
        rows = await session.execute(
            select(Company).join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user_id)
        )
        for c in rows.scalars():
            items.append({"id": str(c.id), "name": f"🏢 {c.name}", "company_id": c.id})
    return items


def _ws_kb(workspaces: List[dict]):
    rows = []
    for w in workspaces:
        rows.append([InlineKeyboardButton(text=w["name"], callback_data=f"wf:ws:{w['id']}")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wf:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _assignee_kb(members: List[dict], prefix: str = "wf:as"):
    rows = []
    for m in members:
        rows.append([InlineKeyboardButton(text=m["name"], callback_data=f"{prefix}:{m['id']}")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wf:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _members_for_workspace(company_id_str: str) -> List[dict]:
    async with get_session() as session:
        if company_id_str == "personal":
            return []
        try:
            cid = int(company_id_str)
        except ValueError:
            return []
        rows = await session.execute(
            select(User).join(CompanyMember, CompanyMember.user_id == User.id)
            .where(CompanyMember.company_id == cid)
        )
        return [{"id": u.id, "name": u.full_name or u.username or f"#{u.id}"}
                for u in rows.scalars()]


# ─── Workflow Detail View ─────────────────────────────────────────────────────

async def _user_can_view_task(session, task: Task, user_id: int) -> bool:
    """Foydalanuvchi vazifani ko'ra oladimi tekshirish.

    Ruxsat: admin (hamma WF), creator, assignee, kompaniya a'zosi, guruh a'zosi.
    """
    # Admin — hammasini ko'radi
    admin_ids = settings.admin_ids_list
    if admin_ids:
        u = await session.get(User, user_id)
        if u and u.telegram_id in admin_ids:
            return True
    if task.creator_id == user_id:
        return True
    # Assignee?
    from database.models import CompanyMember, GroupMember
    asg = await session.execute(
        select(TaskAssignment.id).where(
            TaskAssignment.task_id == task.id,
            TaskAssignment.user_id == user_id,
        )
    )
    if asg.scalar_one_or_none() is not None:
        return True
    # Kompaniya a'zosi?
    if task.company_id:
        cm = await session.execute(
            select(CompanyMember.id).where(
                CompanyMember.company_id == task.company_id,
                CompanyMember.user_id == user_id,
            )
        )
        if cm.scalar_one_or_none() is not None:
            return True
    # Guruh a'zosi?
    if task.group_id:
        gm = await session.execute(
            select(GroupMember.id).where(
                GroupMember.group_id == task.group_id,
                GroupMember.user_id == user_id,
            )
        )
        if gm.scalar_one_or_none() is not None:
            return True
    return False


async def _render_workflow_detail(task_id: int, current_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Workflow detail matni va klaviaturasini qaytaradi."""
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return "❌ Workflow topilmadi.", InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="wf:list")]
            ])

        # Ruxsat tekshiruvi — vazifaga aloqasi yo'q odamga ko'rsatmaymiz
        if not await _user_can_view_task(session, task, current_user_id):
            return (
                "🚫 <b>Bu vazifa sizga tegishli emas.</b>\n\n"
                "<i>Faqat vazifa yaratuvchisi, ijrochilari yoki vazifa "
                "joylashgan jamoa/guruh a'zolari ko'ra oladi.</i>"
            ), InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="wf:list")]
            ])

        # Steps
        sr = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.order_index)
        )
        steps = list(sr.scalars())

        # Subtasks
        subr = await session.execute(
            select(Task).where(Task.parent_id == task_id).order_by(Task.created_at)
        )
        subtasks = list(subr.scalars())

        # Creator
        creator = await session.get(User, task.creator_id)
        creator_name = (creator.full_name or creator.username or "?") if creator else "?"

        # Steps info
        done_n = sum(1 for s in steps if s.status == "done")
        total_n = len(steps)
        cur_step = next((s for s in steps if s.status == "active"), None)

        # Status emoji
        if task.status == TaskStatus.DONE:
            task_em = "✅"
            task_status_txt = "Yakunlangan"
        elif task.status == TaskStatus.CANCELLED:
            task_em = "🚫"
            task_status_txt = "Bekor qilingan"
        elif cur_step:
            task_em = "🔄"
            task_status_txt = "Jarayonda"
        else:
            task_em = "⏸"
            task_status_txt = "To'xtatilgan"

        # ── Text build ──
        lines = [
            f"{task_em} <b>{task.title}</b>  <code>#{task.id}</code>",
            f"👤 Yaratuvchi: {creator_name}",
            f"📊 Holat: {task_status_txt}  •  {done_n}/{total_n} qadam",
        ]
        if task.description:
            lines.append(f"📝 {task.description[:200]}")

        lines.append("\n<b>🪜 QADAMLAR:</b>")
        for s in steps:
            # assignee name
            au = await session.get(User, s.assignee_user_id)
            aname = (au.full_name or au.username or "?") if au else "?"

            if s.status == "done":
                icon = "✅"
            elif s.status == "active":
                icon = "🟢"
            elif s.status == "blocked":
                icon = "⏸"
            else:
                icon = "⚪"

            step_line = f"{icon} <b>{s.order_index+1}. {s.title}</b> — 👤 {aname}"
            if s.status == "active":
                step_line += "  ← <i>hozir</i>"
            lines.append(step_line)
            if s.deadline:
                _TZ2 = ZoneInfo(settings.DEFAULT_TIMEZONE)
                dl_str = s.deadline.astimezone(_TZ2).strftime('%d.%m.%Y %H:%M')
                lines.append(f"   ⏰ Muddat: <i>{dl_str}</i>")
            if s.note:
                lines.append(f"   💬 <i>{s.note[:100]}</i>")

        # Subtasks
        if subtasks:
            lines.append(f"\n<b>📎 SUBTASKLAR ({len(subtasks)}):</b>")
            for st in subtasks[:10]:
                if st.status == TaskStatus.DONE:
                    s_icon = "☑️"
                elif st.status == TaskStatus.CANCELLED:
                    s_icon = "🚫"
                else:
                    s_icon = "☐"
                lines.append(f"  {s_icon} {st.title[:60]}")
            if len(subtasks) > 10:
                lines.append(f"  ... va yana {len(subtasks)-10} ta")
        else:
            lines.append("\n📎 <i>Subtasklar yo'q</i>")

        text = "\n".join(lines)

        # ── Keyboard ──
        kb_rows = []

        # Mening aktiv qadamim bormi?
        my_active = next(
            (s for s in steps if s.status == "active" and s.assignee_user_id == current_user_id),
            None
        )
        if my_active:
            kb_rows.append([InlineKeyboardButton(
                text=f"✅ {my_active.order_index+1}-qadamni tugatish",
                callback_data=f"wfdo:{task_id}"
            )])

        kb_rows.append([
            InlineKeyboardButton(text="💬 Izoh yozish",   callback_data=f"wf:cmt:{task_id}"),
            InlineKeyboardButton(text="➕ Subtask",        callback_data=f"wf:subtask:{task_id}"),
        ])

        kb_rows.append([InlineKeyboardButton(
            text="🔙 Workflow ro'yxati",
            callback_data="wf:list"
        )])

        return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


@router.message(Command("wf"))
async def cmd_wf_detail(message: Message, user: User):
    """/wf <task_id> — workflow detail ko'rish"""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ Foydalanish: <code>/wf [task_id]</code>\n\n"
            "Misol: <code>/wf 42</code>\n\n"
            "Barcha workflow lar: /workflows"
        )
        return
    try:
        task_id = int(parts[1].strip())
    except ValueError:
        await message.answer("❗ task_id raqam bo'lishi kerak.")
        return

    text, kb = await _render_workflow_detail(task_id, user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("wf:view:"))
async def cb_wf_view(callback: CallbackQuery, user: User):
    """Ro'yxatdan workflow ga kirish"""
    try:
        task_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Xato", show_alert=True)
        return

    text, kb = await _render_workflow_detail(task_id, user.id)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "wf:list")
async def cb_wf_list(callback: CallbackQuery, user: User):
    """Workflow ro'yxatiga qaytish"""
    text, kb = await _build_workflows_list(user)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ─── Workflow list builder (shared) ──────────────────────────────────────────

async def _build_workflows_list(user: User) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    async with get_session() as session:
        rows = await session.execute(
            select(Task).join(TaskStep, TaskStep.task_id == Task.id)
            .where(
                (TaskStep.assignee_user_id == user.id) | (Task.creator_id == user.id)
            ).distinct()
        )
        tasks = list(rows.scalars())

        if not tasks:
            return (
                "📭 Sizda workflow vazifa yo'q.\n\nYangisini yaratish: /newworkflow",
                None
            )

        out = "🔗 <b>Workflow vazifalar:</b>\n\n"
        kb_rows = []

        for t in tasks[:20]:
            r2 = await session.execute(
                select(TaskStep).where(TaskStep.task_id == t.id).order_by(TaskStep.order_index)
            )
            sts = list(r2.scalars())
            done_n = sum(1 for s in sts if s.status == "done")
            cur = next((s for s in sts if s.status == "active"), None)

            # subtask count
            subr = await session.execute(
                select(Task).where(Task.parent_id == t.id)
            )
            sub_count = len(list(subr.scalars()))

            if t.status == TaskStatus.DONE:
                status_em = "✅"
            elif cur and cur.status == "blocked":
                status_em = "⏸"
            elif cur:
                status_em = "🔄"
            else:
                status_em = "⏸"

            # Current step assignee
            cur_name = "—"
            if cur:
                au = await session.get(User, cur.assignee_user_id)
                cur_name = (au.full_name or au.username or "?") if au else "?"

            sub_txt = f" | 📎{sub_count}" if sub_count else ""
            out += (
                f"{status_em} <b>#{t.id}</b> {t.title}\n"
                f"   📊 {done_n}/{len(sts)} qadam{sub_txt}  •  👤 {cur_name}\n\n"
            )

            kb_rows.append([InlineKeyboardButton(
                text=f"{status_em} #{t.id} {t.title[:35]}",
                callback_data=f"wf:view:{t.id}"
            )])

        kb_rows.append([InlineKeyboardButton(
            text="➕ Yangi workflow", callback_data="wf:new"
        )])
        return out, InlineKeyboardMarkup(inline_keyboard=kb_rows)


# ─── Workflow izoh yozish (yaratuvchi/ijrochi/kuzatuvchi uchun) ──────────────

@router.callback_query(F.data.startswith("wf:cmt:"))
async def cb_wf_comment_start(callback: CallbackQuery, state: FSMContext, user: User):
    """Workflow vazifaga izoh yozishni boshlash"""
    try:
        task_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Xato", show_alert=True)
        return

    # Ruxsat tekshiruvi
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            await callback.answer("❌ Vazifa topilmadi", show_alert=True)
            return
        if not await _user_can_view_task(session, task, user.id):
            await callback.answer("🚫 Sizda ruxsat yo'q", show_alert=True)
            return
        title_preview = task.title

    await state.set_state(WorkflowStates.waiting_wf_comment)
    await state.update_data(wf_cmt_task_id=task_id, wf_cmt_origin_msg_id=callback.message.message_id)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"wf:cmt_cancel:{task_id}")],
    ])
    try:
        await callback.message.answer(
            f"💬 <b>Izoh yozing</b>\n\n"
            f"📋 Vazifa: <b>{title_preview}</b>\n\n"
            f"<i>Izoh matnini yuboring (1000 belgi gacha).</i>",
            reply_markup=cancel_kb,
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("wf:cmt_cancel:"))
async def cb_wf_comment_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("❌ Izoh bekor qilindi.")
    except Exception:
        try: await callback.message.delete()
        except Exception: pass
    await callback.answer()


@router.message(WorkflowStates.waiting_wf_comment)
async def msg_wf_comment(message: Message, state: FSMContext, user: User, bot: Bot):
    """Workflow izoh matnini saqlash + barcha qatnashchilarga yuborish"""
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗ Izoh matnini yuboring yoki /cancel orqali bekor qiling.")
        return
    if len(text) > 1000:
        await message.answer("❗ Izoh juda uzun (max 1000 belgi). Qisqartirib qayta yuboring.")
        return

    data = await state.get_data()
    task_id = data.get("wf_cmt_task_id")
    if not task_id:
        await state.clear()
        await message.answer("❌ Xato — vazifa aniqlanmadi.")
        return

    # Saqlash
    participants: List[int] = []
    title = ""
    try:
        async with get_session() as session:
            task = await session.get(Task, task_id)
            if not task:
                await state.clear()
                await message.answer("❌ Vazifa topilmadi.")
                return
            title = task.title

            session.add(TaskComment(
                task_id=task_id, user_id=user.id, content=text,
            ))

            # Qatnashchilar — creator + step assignees + observers (TaskAssignment)
            participants.append(task.creator_id)
            step_res = await session.execute(
                select(TaskStep.assignee_user_id).where(TaskStep.task_id == task_id)
            )
            for r in step_res.all():
                if r[0]:
                    participants.append(r[0])
            asg_res = await session.execute(
                select(TaskAssignment.user_id).where(TaskAssignment.task_id == task_id)
            )
            for r in asg_res.all():
                if r[0]:
                    participants.append(r[0])

            await session.commit()
    except Exception as e:
        logger.exception(f"Workflow comment saqlash xatosi: {e}")
        await message.answer("❌ Saqlashda xato.")
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Izoh saqlandi va qatnashchilarga yuborildi.")

    # Bildirishnoma
    unique_ids = list({uid for uid in participants if uid and uid != user.id})
    actor_mention = f"@{user.username}" if user.username else user.full_name
    notify_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Batafsil ko'rish", callback_data=f"wf:view:{task_id}")],
    ])
    msg_text = (
        f"💬 <b>Workflow vazifaga yangi izoh</b>\n\n"
        f"📋 Vazifa: <b>{title}</b>\n"
        f"👤 <b>{actor_mention}</b> yozdi:\n\n"
        f"<i>{text}</i>"
    )
    async with get_session() as session:
        for uid in unique_ids:
            try:
                u = await session.get(User, uid)
                if u and u.telegram_id:
                    await bot.send_message(u.telegram_id, msg_text, reply_markup=notify_kb)
            except Exception as e:
                logger.warning(f"WF comment notify uid={uid}: {e}")


# ─── Subtask qo'shish ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wf:subtask:"))
async def cb_add_subtask(callback: CallbackQuery, state: FSMContext, user: User):
    """Subtask yaratishni boshlash"""
    try:
        parent_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Xato", show_alert=True)
        return

    await state.clear()
    await state.set_state(SubtaskStates.waiting_title)
    await state.update_data(subtask_parent_id=parent_id)

    await callback.message.answer(
        f"📎 <b>Subtask qo'shish</b>\n"
        f"Workflow: <code>#{parent_id}</code>\n\n"
        "Subtask <b>nomini</b> kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"wf:view:{parent_id}")]
        ])
    )
    await callback.answer()


@router.message(SubtaskStates.waiting_title)
async def subtask_title(message: Message, state: FSMContext, user: User):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❗ Nom kamida 2 belgi bo'lsin.")
        return

    await state.update_data(subtask_title=message.text.strip())
    data = await state.get_data()
    parent_id = data.get("subtask_parent_id")

    # Workflow ning workspace a'zolarini olamiz
    async with get_session() as session:
        parent = await session.get(Task, parent_id)
        if not parent:
            await message.answer("❌ Workflow topilmadi.")
            await state.clear()
            return

        members: List[dict] = [{"id": user.id, "name": (user.full_name or user.username or "Men")}]
        if parent.company_id:
            rows = await session.execute(
                select(User).join(CompanyMember, CompanyMember.user_id == User.id)
                .where(CompanyMember.company_id == parent.company_id)
            )
            members = [
                {"id": u.id, "name": u.full_name or u.username or f"#{u.id}"}
                for u in rows.scalars()
            ]
            if not any(m["id"] == user.id for m in members):
                members.insert(0, {"id": user.id, "name": (user.full_name or "Men")})

    await state.update_data(subtask_members=members)
    await state.set_state(SubtaskStates.waiting_assignee)
    await message.answer(
        "👤 <b>Subtaskni kim bajaradi?</b>",
        reply_markup=_assignee_kb(members, prefix="sub:as")
    )


@router.callback_query(SubtaskStates.waiting_assignee, F.data.startswith("sub:as:"))
async def subtask_assignee(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot):
    try:
        assignee_id = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Xato", show_alert=True)
        return

    data = await state.get_data()
    parent_id    = data.get("subtask_parent_id")
    title        = data.get("subtask_title", "Subtask")
    members      = data.get("subtask_members", [])
    assignee     = next((m for m in members if m["id"] == assignee_id), None)
    assignee_name = assignee["name"] if assignee else "?"

    async with get_session() as session:
        parent = await session.get(Task, parent_id)

        subtask = Task(
            title=title,
            status=TaskStatus.NEW,
            priority=Priority.MEDIUM,
            creator_id=user.id,
            parent_id=parent_id,
            company_id=parent.company_id if parent else None,
            group_id=parent.group_id if parent else None,
        )
        session.add(subtask)
        await session.flush()

        # Ijrochini birikitirish
        session.add(TaskAssignment(task_id=subtask.id, user_id=assignee_id, status="new"))
        await session.commit()
        subtask_id = subtask.id

        # Ijrochiga xabar
        if assignee_id != user.id:
            try:
                asn_user = await session.get(User, assignee_id)
                if asn_user and asn_user.telegram_id:
                    await bot.send_message(
                        asn_user.telegram_id,
                        f"📎 <b>Sizga subtask biriktirildi!</b>\n\n"
                        f"📋 Asosiy vazifa: #{parent_id} {parent.title if parent else ''}\n"
                        f"☐ Subtask: <b>{title}</b>\n\n"
                        f"<code>/task {subtask_id}</code> — subtask ko'rish"
                    )
            except Exception as e:
                logger.warning(f"Subtask notify: {e}")

    await state.clear()

    # Detail sahifaga qaytish
    text, kb = await _render_workflow_detail(parent_id, user.id)
    try:
        await callback.message.edit_text(
            f"✅ <b>Subtask qo'shildi!</b>\n"
            f"☐ {title} — 👤 {assignee_name}\n\n" + text,
            reply_markup=kb
        )
    except Exception:
        await callback.message.answer(
            f"✅ Subtask qo'shildi: {title}\n\n" + text,
            reply_markup=kb
        )
    await callback.answer("Subtask yaratildi!")


# ─── Workflow yaratish ────────────────────────────────────────────────────────

@router.message(Command("newworkflow"))
@router.message(F.text == "🔗 Workflow vazifa")
@router.callback_query(F.data == "wf:new")
async def cmd_new_workflow(update, state: FSMContext, user: User):
    message = update if isinstance(update, Message) else update.message
    await state.clear()
    await state.set_state(WorkflowStates.waiting_title)
    await state.update_data(steps=[])
    await message.answer(
        "🔗 <b>Workflow vazifa yaratish</b>\n\n"
        "Bu rejim — vazifa <i>ketma-ket</i> bajariladi.\n"
        "Birinchi odam o'z qismini tugatmaguncha keyingisi boshlanmaydi.\n\n"
        "1-qadam: Vazifa <b>nomini</b> kiriting:",
        reply_markup=_cancel_kb(),
    )
    if isinstance(update, CallbackQuery):
        await update.answer()


@router.message(WorkflowStates.waiting_title)
async def wf_title(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("❗ Nom kamida 3 belgi bo'lsin.")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(WorkflowStates.waiting_description)
    await message.answer(
        "📝 Qisqacha <b>tavsif</b> kiriting (yoki /skip):",
        reply_markup=_cancel_kb(),
    )


@router.message(WorkflowStates.waiting_description, Command("skip"))
async def wf_desc_skip(message: Message, state: FSMContext, user: User):
    await state.update_data(description=None)
    await _ask_workspace(message, state, user)


@router.message(WorkflowStates.waiting_description)
async def wf_desc(message: Message, state: FSMContext, user: User):
    await state.update_data(description=(message.text or "").strip()[:2000])
    await _ask_workspace(message, state, user)


async def _ask_workspace(message: Message, state: FSMContext, user: User):
    data = await state.get_data()
    # Sub-task oqimida workspace allaqachon belgilangan bo'lsa — o'tkazib yuboramiz
    parent_id  = data.get("parent_id")
    company_id = data.get("company_id")
    group_id   = data.get("group_id")
    if parent_id and (company_id or group_id):
        ws_id = str(company_id) if company_id else "personal"
        members = await _members_for_workspace(ws_id)
        if not members and group_id:
            # Group members ni to'g'ridan-to'g'ri olish
            from services.group_service import GroupService as _GS
            async with get_session() as _sess:
                gm_list = await _GS.get_members(_sess, group_id)
            members = [{"id": m.user_id, "name": m.user.full_name or m.user.username or f"#{m.user_id}"}
                       for m in gm_list if m.user]
        if not members:
            members = [{"id": user.id, "name": (user.full_name or user.username or "Men")}]
        await state.update_data(workspace_id=ws_id, members=members)
        await state.set_state(WorkflowStates.waiting_step_title)
        steps = data.get("steps", [])
        await message.answer(
            f"🪜 <b>{len(steps)+1}-qadam tavsifi:</b> Bu odam nima qilishi kerak?",
            reply_markup=_cancel_kb(),
        )
        return

    workspaces = await _get_user_workspaces(user.id)
    await state.update_data(_workspaces=workspaces)
    await state.set_state(WorkflowStates.waiting_workspace)
    await message.answer(
        "📁 <b>Workspace tanlang</b> — bu yerdagi a'zolar qadam ijrochilari bo'ladi:",
        reply_markup=_ws_kb(workspaces),
    )


@router.callback_query(WorkflowStates.waiting_workspace, F.data.startswith("wf:ws:"))
async def wf_ws(callback: CallbackQuery, state: FSMContext, user: User):
    ws_id = callback.data.split(":", 2)[2]
    members = await _members_for_workspace(ws_id)
    if ws_id == "personal" or not members:
        members = [{"id": user.id, "name": (user.full_name or user.username or "Men")}]

    await state.update_data(workspace_id=ws_id, members=members)
    await state.set_state(WorkflowStates.waiting_step_title)
    steps = (await state.get_data()).get("steps", [])
    await callback.message.edit_text(
        f"✅ Workspace tanlandi.\n\n"
        f"🪜 <b>{len(steps)+1}-qadam tavsifi:</b> Bu odam nima qilishi kerak?",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.message(WorkflowStates.waiting_step_title)
async def wf_step_title(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("❗ Qadam tavsifi kamida 2 belgi bo'lsin.")
        return
    await state.update_data(_pending_step_title=message.text.strip()[:500])
    data = await state.get_data()
    members = data.get("members", [])
    await state.set_state(WorkflowStates.waiting_step_assignee)
    await message.answer(
        "👤 <b>Bu qadamni kim bajaradi?</b>",
        reply_markup=_assignee_kb(members),
    )


@router.callback_query(WorkflowStates.waiting_step_assignee, F.data.startswith("wf:as:"))
async def wf_step_assignee(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split(":", 2)[2])
    data = await state.get_data()
    members = data.get("members", [])
    member = next((m for m in members if m["id"] == user_id), None)
    if not member:
        await callback.answer("Topilmadi", show_alert=True)
        return

    await state.update_data(_pending_assignee_id=user_id, _pending_assignee_name=member["name"])
    await state.set_state(WorkflowStates.waiting_step_deadline)

    from zoneinfo import ZoneInfo as _ZI
    _now = datetime.now(_ZI(settings.DEFAULT_TIMEZONE))
    _ex_date = _now.strftime("%d.%m.%Y")
    _ex_dt   = _now.strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text(
        f"⏰ <b>Bu qadam uchun muddat?</b>\n\n"
        f"👤 Kuzatuvchi: <b>{member['name']}</b>\n\n"
        f"✅ <b>Tavsiya — necha KUN:</b> <code>3</code> yoki <code>5 kun</code>\n"
        f"<i>Muddat qadam navbati kelganda boshlanadi — oldingi odam kechiksa ham "
        f"bu odam to'liq muddatini oladi.</i>\n\n"
        f"📅 Aniq sana ham mumkin: <code>{_ex_date}</code> yoki <code>{_ex_dt}</code>\n\n"
        "Muddat yo'q bo'lsa — /skip yuboring",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


def _parse_step_deadline(text: str) -> Optional[datetime]:
    """Matndan deadline parse qilish, Asia/Tashkent TZ bilan."""
    from zoneinfo import ZoneInfo as _ZI
    _TZ = _ZI(settings.DEFAULT_TIMEZONE)
    text = text.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.replace(tzinfo=_TZ)
        except ValueError:
            continue
    return None


def _parse_step_days(text: str) -> Optional[int]:
    """«3», «5 kun», «7kun» → kun soni (nisbiy muddat)."""
    import re as _re
    t = (text or "").strip().lower().replace("kun", "").replace("kunlik", "").strip()
    if not t:
        return None
    m = _re.fullmatch(r"\d{1,3}", t)
    if not m:
        return None
    n = int(t)
    return n if 1 <= n <= 365 else None


def _step_deadline_text(step: dict) -> str:
    d = step.get("duration_days")
    if d:
        return f" | ⏳ {d} kun (navbat kelganda boshlanadi)"
    dl = step.get("deadline")
    if not dl:
        return ""
    from zoneinfo import ZoneInfo as _ZI
    _TZ = _ZI(settings.DEFAULT_TIMEZONE)
    if isinstance(dl, str):
        return f" | ⏰ {dl}"
    try:
        return f" | ⏰ {dl.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}"
    except Exception:
        return ""


@router.message(WorkflowStates.waiting_step_deadline, Command("skip"))
async def wf_step_deadline_skip(message: Message, state: FSMContext):
    await _save_step_and_continue(message, state, deadline=None)


@router.message(WorkflowStates.waiting_step_deadline)
async def wf_step_deadline(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❗ Matn yuboring yoki /skip")
        return

    # 1) Avval «N kun» (nisbiy muddat) — tavsiya etilgan usul
    days = _parse_step_days(message.text)
    if days:
        await _save_step_and_continue(message, state, deadline=None, duration_days=days)
        return

    # 2) Aniq sana
    dl = _parse_step_deadline(message.text)
    if not dl:
        from zoneinfo import ZoneInfo as _ZI
        _now = datetime.now(_ZI(settings.DEFAULT_TIMEZONE))
        _ex_date = _now.strftime("%d.%m.%Y")
        await message.answer(
            f"❗ Format noto'g'ri.\n\n"
            f"✅ Necha kun: <code>3</code> yoki <code>5 kun</code>\n"
            f"📅 Yoki sana: <code>{_ex_date}</code>\n"
            "Muddat yo'q bo'lsa: /skip"
        )
        return
    await _save_step_and_continue(message, state, deadline=dl)


def _steps_summary(steps: List[dict]) -> str:
    """Qadamlar ro'yxati + nisbiy muddatlar uchun TAXMINIY sanalar zanjiri.

    Misol:  #1 → 05.08 (aniq),  #2 → 2 kun ⇒ ≈ 07.08,  #3 → 3 kun ⇒ ≈ 10.08
    """
    from zoneinfo import ZoneInfo as _ZI
    _TZ = _ZI(settings.DEFAULT_TIMEZONE)
    cursor = None
    out = ""
    for i, s in enumerate(steps, 1):
        dl = s.get("deadline")
        dur = s.get("duration_days")
        info = ""
        if dl:
            try:
                cursor = dl
                info = f" | ⏰ {dl.astimezone(_TZ).strftime('%d.%m.%Y %H:%M')}"
            except Exception:
                info = ""
        elif dur:
            base = cursor or datetime.now(_TZ)
            est = base + timedelta(days=int(dur))
            cursor = est
            info = f" | ⏳ {dur} kun ⇒ ≈ {est.astimezone(_TZ).strftime('%d.%m.%Y')}"
        out += f"{i}. <b>{s['title']}</b>\n   👤 {s['assignee_name']}{info}\n\n"
    return out


async def _save_step_and_continue(message: Message, state: FSMContext, deadline, duration_days=None):
    data = await state.get_data()
    steps = data.get("steps", [])
    steps.append({
        "title": data.get("_pending_step_title", "—"),
        "assignee_id": data.get("_pending_assignee_id"),
        "assignee_name": data.get("_pending_assignee_name", "?"),
        "deadline": deadline,
        "duration_days": duration_days,
    })
    await state.update_data(steps=steps, _pending_step_title=None,
                            _pending_assignee_id=None, _pending_assignee_name=None)
    await state.set_state(WorkflowStates.waiting_more_steps)

    txt = "<b>📋 Workflow qadamlari hozir:</b>\n\n" + _steps_summary(steps)
    txt += "Yana qadam qo'shasizmi?"
    await message.answer(txt, reply_markup=_more_kb())


@router.callback_query(WorkflowStates.waiting_more_steps, F.data == "wf:add_more")
async def wf_add_more(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    steps = data.get("steps", [])
    await state.set_state(WorkflowStates.waiting_step_title)
    await callback.message.answer(
        f"🪜 <b>{len(steps)+1}-qadam tavsifi:</b> Bu odam nima qilishi kerak?",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


def _observers_kb(members: List[dict], selected_ids: set) -> InlineKeyboardMarkup:
    """Kuzatuvchilarni multi-select qilish klaviaturasi"""
    rows = []
    for m in members:
        mark = "☑️" if m["id"] in selected_ids else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {m['name']}",
            callback_data=f"wf:obs:tog:{m['id']}",
        )])
    rows.append([
        InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="wf:obs:skip"),
        InlineKeyboardButton(text="✅ Tayyor",              callback_data="wf:obs:done"),
    ])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wf:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_workflow_members(state_data: dict, creator: User) -> List[dict]:
    """Kuzatuvchi sifatida tanlash mumkin bo'lgan a'zolar.
    Workspace tanlanganda state['members'] ga saqlangan ro'yxatdan foydalanamiz
    (group/kompaniya a'zolari to'liq mavjud)."""
    cached = state_data.get("members") or []
    # Workflow qadam ijrochilarini ro'yxatdan olib tashlash, lekin yaratuvchini qoldiramiz —
    # ba'zan creator ham kuzatuvchi bo'lib turishni xohlasa kerak, lekin u allaqachon
    # bildirishnoma oladi, shuning uchun uni ham olib tashlaymiz.
    existing_step_ids = {s["assignee_id"] for s in state_data.get("steps", [])}
    existing_step_ids.add(creator.id)
    members = [m for m in cached if m["id"] not in existing_step_ids]
    return members


@router.callback_query(WorkflowStates.waiting_more_steps, F.data == "wf:finish")
async def wf_finish_to_observers(callback: CallbackQuery, state: FSMContext, user: User):
    """Steps tugadi — endi kuzatuvchi tanlash bosqichiga o'tamiz"""
    data = await state.get_data()
    steps = data.get("steps", [])
    if len(steps) < 1:
        await callback.answer("Kamida 1 ta qadam kerak", show_alert=True)
        return

    members = await _load_workflow_members(data, user)
    if not members:
        # Tanlash uchun a'zo yo'q — to'g'ridan-to'g'ri saqlash
        await _wf_save(callback, state, user, callback.bot, observer_ids=[])
        return

    await state.update_data(observer_ids=[])
    await state.set_state(WorkflowStates.waiting_observers)
    text = (
        f"👁 <b>Kuzatuvchilar tanlang</b> (ixtiyoriy)\n\n"
        f"Tanlangan kuzatuvchilar:\n"
        f"  • Workflow yaratilganda xabar oladi\n"
        f"  • Har qadam holati o'zgarganda kuzatib boradi\n"
        f"  • Izoh/fayl yuklanganda xabardor bo'ladi\n\n"
        f"<i>{len(members)} a'zo</i>"
    )
    try:
        await callback.message.edit_text(text, reply_markup=_observers_kb(members, set()))
    except Exception:
        await callback.message.answer(text, reply_markup=_observers_kb(members, set()))
    await callback.answer()


@router.callback_query(WorkflowStates.waiting_observers, F.data.startswith("wf:obs:tog:"))
async def wf_observers_toggle(callback: CallbackQuery, state: FSMContext, user: User):
    uid = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = set(data.get("observer_ids", []))
    if uid in selected:
        selected.discard(uid)
    else:
        selected.add(uid)
    await state.update_data(observer_ids=list(selected))
    members = await _load_workflow_members(data, user)
    try:
        await callback.message.edit_reply_markup(reply_markup=_observers_kb(members, selected))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(WorkflowStates.waiting_observers, F.data == "wf:obs:skip")
async def wf_observers_skip(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot):
    await _wf_save(callback, state, user, bot, observer_ids=[])


@router.callback_query(WorkflowStates.waiting_observers, F.data == "wf:obs:done")
async def wf_observers_done(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot):
    data = await state.get_data()
    obs_ids = list(set(data.get("observer_ids", [])))
    await _wf_save(callback, state, user, bot, observer_ids=obs_ids)


async def _wf_save(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot, observer_ids: List[int]):
    """Workflow'ni saqlash + kuzatuvchilarni biriktirish + bildirishnomalar"""
    data = await state.get_data()
    steps = data.get("steps", [])
    if len(steps) < 1:
        await callback.answer("Kamida 1 ta qadam kerak", show_alert=True)
        return

    title      = data.get("title", "Workflow vazifa")
    desc       = data.get("description")
    ws_id      = data.get("workspace_id", "personal")
    company_id = data.get("company_id")   # Sub-task oqimidan meros
    parent_id  = data.get("parent_id")
    if not company_id and ws_id != "personal":
        try: company_id = int(ws_id)
        except ValueError: pass

    task_id = None
    try:
        async with get_session() as session:
            task = Task(
                title=title,
                description=desc,
                priority=Priority.MEDIUM,
                status=TaskStatus.IN_PROGRESS,
                creator_id=user.id,
                company_id=company_id,
                parent_id=parent_id,
            )
            session.add(task)
            await session.flush()

            _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
            # Bir foydalanuvchi bir necha qadamda mas'ul bo'lishi mumkin —
            # uq_task_user (task_id, user_id) constraint buzilmasligi uchun
            # TaskAssignment bir userga atigi bir martaga qo'shamiz.
            seen_assignees = set()
            _now_tz = datetime.now(_TZ)
            for i, s in enumerate(steps):
                _dur = s.get("duration_days")
                _dl = s.get("deadline")
                # Birinchi qadam darrov aktiv — nisbiy muddat bo'lsa shu paytdan hisoblaymiz
                if i == 0 and _dur and not _dl:
                    _dl = _now_tz + timedelta(days=int(_dur))
                session.add(TaskStep(
                    task_id=task.id,
                    order_index=i,
                    title=s["title"],
                    assignee_user_id=s["assignee_id"],
                    status="active" if i == 0 else "pending",
                    started_at=_now_tz if i == 0 else None,
                    deadline=_dl,
                    duration_days=_dur,
                ))
                aid = s["assignee_id"]
                if aid not in seen_assignees:
                    seen_assignees.add(aid)
                    session.add(TaskAssignment(
                        task_id=task.id, user_id=aid, status="new",
                        is_responsible=True,
                    ))

            # Kuzatuvchilarni qo'shish (is_responsible=False)
            observers_added = []
            for obs_id in observer_ids:
                if obs_id in seen_assignees or obs_id == user.id:
                    continue  # ijrochi yoki yaratuvchi bo'lgan bo'lsa, skip
                seen_assignees.add(obs_id)
                session.add(TaskAssignment(
                    task_id=task.id, user_id=obs_id, status="new",
                    is_responsible=False,
                ))
                observers_added.append(obs_id)

            await session.commit()
            task_id = task.id
            logger.info(
                f"Workflow saqlandi: task_id={task_id}, creator={user.id}, "
                f"steps={len(steps)}, ijrochi={len(seen_assignees) - len(observers_added)}, "
                f"kuzatuvchi={len(observers_added)}"
            )

            # Inline tugma — workflow detalini darrov ochish
            wf_view_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Batafsil ko'rish", callback_data=f"wf:view:{task_id}")],
            ])

            # Birinchi ijrochiga xabar
            first = steps[0]
            try:
                first_user = await session.get(User, first["assignee_id"])
                if first_user and first_user.telegram_id:
                    await bot.send_message(
                        first_user.telegram_id,
                        f"🔔 <b>Sizga workflow qadami biriktirildi!</b>\n\n"
                        f"📋 Vazifa: <b>{title}</b>\n"
                        f"🪜 1-qadam: <b>{first['title']}</b>\n\n"
                        f"Tugatgach: <code>/done {task_id}</code>",
                        reply_markup=wf_view_kb,
                    )
            except Exception as e:
                logger.warning(f"Workflow notify xato: {e}")

            # Kuzatuvchilarga xabar
            for obs_id in observers_added:
                try:
                    obs = await session.get(User, obs_id)
                    if obs and obs.telegram_id:
                        await bot.send_message(
                            obs.telegram_id,
                            f"👁 <b>Siz workflow kuzatuvchisi sifatida belgilandingiz</b>\n\n"
                            f"📋 Vazifa: <b>{title}</b>\n"
                            f"🪜 Qadamlar soni: <b>{len(steps)}</b>\n"
                            f"✍️ Yaratuvchi: <b>{user.full_name}</b>\n\n"
                            f"Har qadam holati o'zgarganda yoki izoh/fayl yuklanganda "
                            f"siz xabardor bo'lasiz.",
                            reply_markup=wf_view_kb,
                        )
                except Exception as e:
                    logger.warning(f"Observer notify xato uid={obs_id}: {e}")
    except Exception as e:
        # Saqlash xato bersa — FSM holatini SAQLAB qoldiramiz va aniq xabar yuboramiz
        logger.exception(f"Workflow saqlashda xato: {e}")
        try:
            await callback.answer("❌ Saqlashda xatolik", show_alert=True)
        except Exception:
            pass
        try:
            await callback.message.answer(
                f"❌ <b>Workflow saqlashda xatolik yuz berdi.</b>\n\n"
                f"<i>Xato: {type(e).__name__}</i>\n\n"
                f"Qadamlaringiz <b>saqlangan</b> — qaytadan "
                f"<b>«✅ Tugallash va saqlash»</b> tugmasini bosing.\n\n"
                f"Agar xato takrorlansa, qadamlardagi ijrochilarni qayta tekshiring.",
            )
        except Exception:
            pass
        return  # state.clear() chaqirilmaydi — qadamlar saqlangan qoladi

    _TZ_sum = ZoneInfo(settings.DEFAULT_TIMEZONE)
    summary = f"✅ <b>Workflow vazifa yaratildi!</b>\n\n📋 {title}\n\n<b>Qadamlar:</b>\n"
    _cursor = None
    for i, s in enumerate(steps, 1):
        marker = "🟢" if i == 1 else "⚪"
        dl = s.get("deadline")
        dur = s.get("duration_days")
        if dl:
            _cursor = dl
            dl_txt = f" | ⏰ {dl.astimezone(_TZ_sum).strftime('%d.%m.%Y %H:%M')}"
        elif dur:
            _base = _cursor or datetime.now(_TZ_sum)
            _est = _base + timedelta(days=int(dur))
            _cursor = _est
            dl_txt = f" | ⏳ {dur} kun ⇒ ≈ {_est.astimezone(_TZ_sum).strftime('%d.%m.%Y')}"
        else:
            dl_txt = ""
        summary += f"{marker} {i}. {s['title']} — 👤 {s['assignee_name']}{dl_txt}\n"
    obs_count = len(observer_ids)
    summary += f"\n💡 Birinchi ijrochiga bildirishnoma yuborildi."
    if obs_count:
        summary += f"\n👁 Kuzatuvchilar: <b>{obs_count}</b> ta — ularga ham xabar yuborildi."

    wf_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Workflow ko'rish", callback_data=f"wf:view:{task_id}")],
        [InlineKeyboardButton(text="➕ Subtask qo'shish",  callback_data=f"wf:subtask:{task_id}")],
    ])
    try:
        await callback.message.edit_text(summary, reply_markup=wf_kb)
    except Exception:
        try:
            await callback.message.answer(summary, reply_markup=wf_kb)
        except Exception:
            pass
    await callback.answer("Tayyor!")
    await state.clear()


@router.callback_query(F.data == "wf:cancel")
async def wf_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("❌ Workflow yaratish bekor qilindi.")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer("❌ Bekor qilindi")


# ─── /step /done — qadam tugatish (FSM) ─────────────────────────────────────

@router.message(Command("step"))
@router.message(Command("done"))
async def cmd_step_complete(message: Message, state: FSMContext, user: User):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>Qadamni tugatish:</b>\n\n"
            "<code>/step [task_id]</code> yoki <code>/done [task_id]</code>\n\n"
            "Misol: <code>/step 42</code>"
        )
        return
    try:
        task_id = int(parts[1].strip().split()[0])
    except ValueError:
        await message.answer("❗ task_id raqam bo'lishi kerak.")
        return

    async with get_session() as session:
        rows = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.order_index)
        )
        steps = list(rows.scalars())
        if not steps:
            await message.answer("⚠️ Bu vazifada workflow qadamlari yo'q.")
            return

        cur = next((s for s in steps if s.status == "active"), None)
        if not cur:
            await message.answer("⚠️ Aktiv qadam yo'q.")
            return
        if cur.assignee_user_id != user.id:
            await message.answer("🚫 Bu qadam sizga biriktirilmagan.")
            return
        task = await session.get(Task, task_id)

    await state.clear()
    await state.update_data(sc_task_id=task_id, sc_step_id=cur.id, sc_files=[])
    await state.set_state(StepCompleteStates.choosing_status)
    await message.answer(
        f"🪜 <b>Qadam {cur.order_index+1}: {cur.title}</b>\n"
        f"📋 Vazifa: <b>{task.title if task else '—'}</b>\n\n"
        "Qanday holat bermoqchisiz?",
        reply_markup=_step_status_kb(task_id),
    )


@router.callback_query(F.data == "sc:cancel")
async def sc_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("❌ Qadam tugatish bekor qilindi.")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer("❌ Bekor qilindi")


@router.callback_query(StepCompleteStates.choosing_status, F.data.startswith("sc:done:"))
@router.callback_query(StepCompleteStates.choosing_status, F.data.startswith("sc:blocked:"))
async def sc_choose_status(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    status = parts[1]
    await state.update_data(sc_status=status)
    await state.set_state(StepCompleteStates.waiting_comment)
    pref = "✅ Tugatilmoqda" if status == "done" else "⏸ To'xtatilmoqda (blocked)"
    await callback.message.edit_text(
        f"{pref}\n\n💬 <b>Izoh qoldiring</b> — nimani bajardingiz, qanday natija?\n\n"
        "Matn yuboring yoki <b>/skip</b>",
    )
    await callback.answer()


@router.message(StepCompleteStates.waiting_comment, Command("skip"))
async def sc_skip_comment(message: Message, state: FSMContext):
    await state.update_data(sc_comment=None)
    await state.set_state(StepCompleteStates.waiting_files)
    await message.answer(
        "📎 <b>Fayl, rasm yoki video yuborishingiz mumkin</b> (ixtiyoriy).\n\n"
        "Yuborib bo'lgach <b>✅ Tayyor</b> tugmasini bosing, yoki <b>⏭ Faylsiz</b>.",
        reply_markup=_step_files_kb(),
    )


@router.message(StepCompleteStates.waiting_comment)
async def sc_get_comment(message: Message, state: FSMContext):
    # Agar media yuborilsa — izohsiz to'g'ridan faylga o'tamiz
    if not message.text:
        # Media bo'lsa — fayllar bosqichiga o'tib, o'sha mediani qabul qilamiz
        await state.update_data(sc_comment=None)
        await state.set_state(StepCompleteStates.waiting_files)
        # Mediani o'sha yerda qayta ishlaymiz
        f = _extract_file_meta(message)
        if f:
            await state.update_data(sc_files=[f])
            em = {"photo":"🖼","video":"🎥","video_note":"⭕","document":"📄","audio":"🎵","voice":"🎙"}.get(f["file_type"],"📎")
            await message.answer(
                f"{em} <b>{f['file_name']}</b> qo'shildi (1/10).\n\n"
                "Yana yuboring yoki ✅ Tayyor bosing.",
                reply_markup=_step_files_kb(),
            )
        else:
            await message.answer(
                "📎 <b>Fayl, rasm yoki video yuborishingiz mumkin</b> (ixtiyoriy).\n\n"
                "Yuborib bo'lgach <b>✅ Tayyor</b> tugmasini bosing, yoki <b>⏭ Faylsiz</b>.",
                reply_markup=_step_files_kb(),
            )
        return

    await state.update_data(sc_comment=message.text.strip()[:2000])
    await state.set_state(StepCompleteStates.waiting_files)
    await message.answer(
        "📎 <b>Fayl, rasm yoki video yuborishingiz mumkin</b> (ixtiyoriy).\n\n"
        "Yuborib bo'lgach <b>✅ Tayyor</b> tugmasini bosing, yoki <b>⏭ Faylsiz</b>.",
        reply_markup=_step_files_kb(),
    )


@router.message(
    StepCompleteStates.waiting_files,
    F.content_type.in_({"photo", "video", "video_note", "document", "audio", "voice", "animation"})
)
async def sc_collect_file(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("sc_files") or []
    if len(files) >= 10:
        await message.answer("⚠️ Max 10 ta fayl. ✅ Tayyor bosing.")
        return

    f = _extract_file_meta(message)
    if not f:
        await message.answer("❗ Faylni aniqlab bo'lmadi.")
        return
    if f["file_size"] and f["file_size"] > 50 * 1024 * 1024:
        await message.answer("⚠️ Fayl 50MB dan katta.")
        return

    files.append(f)
    await state.update_data(sc_files=files)
    em = {"photo":"🖼","video":"🎥","video_note":"⭕","document":"📄","audio":"🎵","voice":"🎙"}.get(f["file_type"],"📎")
    await message.answer(
        f"{em} <b>{f['file_name']}</b> qo'shildi ({len(files)}/10).\n\n"
        "Yana yuboring yoki ✅ Tayyor bosing.",
        reply_markup=_step_files_kb(),
    )


def _extract_file_meta(message: Message) -> Optional[dict]:
    if message.photo:
        p = max(message.photo, key=lambda x: (x.width or 0) * (x.height or 0))
        return {"file_id": p.file_id, "file_type": "photo",
                "file_name": f"photo_{p.file_unique_id}.jpg",
                "file_size": p.file_size, "mime_type": "image/jpeg"}
    if message.video:
        v = message.video
        return {"file_id": v.file_id, "file_type": "video",
                "file_name": v.file_name or f"video_{v.file_unique_id}.mp4",
                "file_size": v.file_size, "mime_type": v.mime_type or "video/mp4"}
    if message.document:
        d = message.document
        return {"file_id": d.file_id, "file_type": "document",
                "file_name": d.file_name or f"doc_{d.file_unique_id}",
                "file_size": d.file_size, "mime_type": d.mime_type}
    if message.audio:
        a = message.audio
        return {"file_id": a.file_id, "file_type": "audio",
                "file_name": a.file_name or f"audio_{a.file_unique_id}.mp3",
                "file_size": a.file_size, "mime_type": a.mime_type or "audio/mpeg"}
    if message.voice:
        vo = message.voice
        return {"file_id": vo.file_id, "file_type": "voice",
                "file_name": f"voice_{vo.file_unique_id}.ogg",
                "file_size": vo.file_size, "mime_type": "audio/ogg"}
    if message.video_note:
        vn = message.video_note
        return {"file_id": vn.file_id, "file_type": "video_note",
                "file_name": f"videonote_{vn.file_unique_id}.mp4",
                "file_size": vn.file_size, "mime_type": "video/mp4"}
    if message.animation:
        an = message.animation
        return {"file_id": an.file_id, "file_type": "video",
                "file_name": an.file_name or f"gif_{an.file_unique_id}.mp4",
                "file_size": an.file_size, "mime_type": an.mime_type or "video/mp4"}
    return None


@router.callback_query(StepCompleteStates.waiting_files, F.data == "sc:nofiles")
@router.callback_query(StepCompleteStates.waiting_files, F.data == "sc:finish")
async def sc_finish(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot):
    data = await state.get_data()
    task_id = data.get("sc_task_id")
    step_id = data.get("sc_step_id")
    status  = data.get("sc_status")
    comment = data.get("sc_comment")
    files   = data.get("sc_files") or []

    await _persist_step_completion(
        bot=bot, user=user, task_id=task_id, step_id=step_id,
        status=status, comment=comment, files=files,
        reply_to=callback.message,
    )
    await state.clear()
    await callback.answer()


async def _persist_step_completion(
    bot: Bot, user: User, task_id: int, step_id: int,
    status: str, comment: Optional[str], files: list, reply_to: Message,
):
    async with get_session() as session:
        cur = await session.get(TaskStep, step_id)
        if not cur or cur.status != "active":
            await reply_to.answer("⚠️ Qadam aktiv emas yoki topilmadi.")
            return

        if comment:
            session.add(TaskStepComment(step_id=cur.id, user_id=user.id, content=comment))
            cur.note = comment[:500]

        for f in files:
            session.add(TaskStepAttachment(
                step_id=cur.id, user_id=user.id,
                file_type=f.get("file_type", "document"),
                file_id=f.get("file_id"),
                file_name=f.get("file_name"),
                file_size=f.get("file_size"),
                mime_type=f.get("mime_type"),
            ))

        _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)

        # ── Yaratuvchi tasdig'i — agar ijrochi yaratuvchi emas va done deb belgilamoqchi ──
        task = await session.get(Task, task_id)
        if status == "done" and task and user.id != task.creator_id:
            # Qadamni "review" ga qo'yamiz — yaratuvchi tasdiqlashini kutadi
            cur.status = "review"
            cur.completed_at = None
            await session.commit()

            creator = await session.get(User, task.creator_id)
            if creator and creator.telegram_id:
                appr_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"wfappr:ok:{step_id}:{user.id}"),
                    InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"wfappr:no:{step_id}:{user.id}"),
                ]])
                files_txt = f"\n📎 Fayllar: {len(files)} ta" if files else ""
                cmt_txt = f"\n💬 Izoh: <i>{comment[:200]}</i>" if comment else ""
                msg = (
                    f"⏳ <b>Workflow qadami tasdiqlash kutilmoqda</b>\n\n"
                    f"📋 Vazifa: <b>{task.title}</b>\n"
                    f"🪜 Qadam {cur.order_index+1}: <b>{cur.title}</b>\n"
                    f"👤 Ijrochi: <b>{user.full_name}</b>"
                    f"{cmt_txt}{files_txt}\n\n"
                    f"Bu qadamni tasdiqlaysizmi?"
                )
                try:
                    await bot.send_message(creator.telegram_id, msg, reply_markup=appr_kb)
                except Exception as e:
                    logger.warning(f"WF approval req xato: {e}")

            await reply_to.answer(
                f"⏳ <b>Yaratuvchi tasdiqlashini kutmoqda</b>\n\n"
                f"🪜 Qadam {cur.order_index+1}: {cur.title}\n"
                f"Tasdiqlanganida sizga xabar keladi va keyingi qadam ochiladi."
            )
            return

        cur.status       = status
        cur.completed_at = datetime.now(_TZ) if status == "done" else None

        sr = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.order_index)
        )
        steps = list(sr.scalars())
        nxt   = next((s for s in steps if s.order_index == cur.order_index + 1), None)

        finished_all = False
        if status == "done" and nxt:
            activate_step(nxt, datetime.now(_TZ))
        elif status == "done" and not nxt:
            task = await session.get(Task, task_id)
            if task:
                task.status       = TaskStatus.DONE
                task.completed_at = datetime.now(_TZ)
            finished_all = True

        await session.commit()

        task    = await session.get(Task, task_id)
        creator = await session.get(User, task.creator_id) if task else None

        status_icon = "✅" if status == "done" else "⏸"
        status_word = "tugatildi" if status == "done" else "to'xtatildi"
        summary = (
            f"{status_icon} <b>Qadamingiz {status_word}!</b>\n\n"
            f"🪜 Qadam {cur.order_index+1}: {cur.title}\n"
        )
        if comment:
            summary += f"💬 Izoh: <i>{comment[:200]}</i>\n"
        if files:
            summary += f"📎 Fayllar: {len(files)} ta\n"

        if status == "done" and nxt:
            summary += f"\n➡️ Navbatdagi qadam aktivlashtirildi."
            try:
                nu = await session.get(User, nxt.assignee_user_id)
                if nu and nu.telegram_id:
                    msg = (
                        f"🔔 <b>Sizning navbatingiz keldi!</b>\n\n"
                        f"📋 Vazifa #{task_id}: <b>{task.title if task else ''}</b>\n"
                        f"🪜 Qadam {nxt.order_index+1}: <b>{nxt.title}</b>\n\n"
                        f"Ko'rish: /wf {task_id}\n"
                    )
                    if comment:
                        msg += f"Oldingi izoh: 💬 <i>{comment[:200]}</i>\n\n"
                    msg += f"Tugatgach: <code>/step {task_id}</code>"
                    await bot.send_message(nu.telegram_id, msg)
            except Exception as e:
                logger.warning(f"WF next notify: {e}")

        elif status == "done" and finished_all:
            summary += f"\n🎉 Butun workflow yakunlandi!"
            try:
                if creator and creator.telegram_id and creator.id != user.id:
                    await bot.send_message(
                        creator.telegram_id,
                        f"🎉 Workflow <b>{task.title}</b> (#{task_id}) to'liq tugatildi!\n\n"
                        f"/wf {task_id} — natijalarni ko'ring"
                    )
            except Exception:
                pass

        elif status == "blocked":
            summary += f"\n⏸ Workflow to'xtatildi. Yaratuvchiga xabar yuborildi."
            try:
                if creator and creator.telegram_id and creator.id != user.id:
                    blk = (
                        f"⚠️ <b>Workflow to'xtatildi!</b>\n\n"
                        f"📋 Vazifa #{task_id}: {task.title if task else ''}\n"
                        f"🪜 Qadam {cur.order_index+1} ({user.full_name}) — blocked"
                    )
                    if comment:
                        blk += f"\n\n💬 Sababi: <i>{comment[:400]}</i>"
                    await bot.send_message(creator.telegram_id, blk)
            except Exception:
                pass

        # Detail ko'rinishga qaytish tugmasi
        view_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Workflow ko'rish", callback_data=f"wf:view:{task_id}")]
        ])
        try:
            await reply_to.edit_text(summary, reply_markup=view_kb)
        except Exception:
            await reply_to.answer(summary, reply_markup=view_kb)


# ─── /workflows — ro'yxat ────────────────────────────────────────────────────

@router.message(Command("workflows"))
async def cmd_my_workflows(message: Message, user: User):
    text, kb = await _build_workflows_list(user)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("wfdo:"))
async def cb_start_step_complete(callback: CallbackQuery, state: FSMContext, user: User):
    """/workflows ro'yxatidan qadam tugatishni boshlash"""
    try:
        task_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Xato", show_alert=True)
        return

    async with get_session() as session:
        rows = await session.execute(
            select(TaskStep).where(
                TaskStep.task_id == task_id,
                TaskStep.status  == "active",
                TaskStep.assignee_user_id == user.id,
            )
        )
        cur = rows.scalar_one_or_none()
        if not cur:
            await callback.answer("Sizning aktiv qadamingiz yo'q", show_alert=True)
            return
        task = await session.get(Task, task_id)

    await state.clear()
    await state.update_data(sc_task_id=task_id, sc_step_id=cur.id, sc_files=[])
    await state.set_state(StepCompleteStates.choosing_status)
    await callback.message.answer(
        f"🪜 <b>Qadam {cur.order_index+1}: {cur.title}</b>\n"
        f"📋 Vazifa: <b>{task.title if task else '—'}</b>\n\n"
        "Qanday holat bermoqchisiz?",
        reply_markup=_step_status_kb(task_id),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════
# Workflow QADAM tasdig'i — yaratuvchi mas'ulning "Bajarildi"sini tasdiqlaydi
# ═══════════════════════════════════════════════════════════════════════════

class WfApprovalStates(StatesGroup):
    waiting_comment = State()


@router.callback_query(F.data.startswith("wfappr:"))
async def cb_wf_approval_action(callback: CallbackQuery, state: FSMContext, user: User):
    """wfappr:ok|no:<step_id>:<actor_id>"""
    try:
        parts = callback.data.split(":")
        action = parts[1]
        if action == "cancel":
            await state.clear()
            try:
                await callback.message.edit_text("ℹ️ Tasdiqlash bekor qilindi.")
            except Exception:
                pass
            await callback.answer()
            return
        step_id = int(parts[2])
        actor_id = int(parts[3])
    except Exception:
        await callback.answer("Xato", show_alert=True)
        return

    async with get_session() as session:
        step = await session.get(TaskStep, step_id)
        if not step:
            await callback.answer("Qadam topilmadi", show_alert=True)
            return
        task = await session.get(Task, step.task_id)
        if not task or task.creator_id != user.id:
            await callback.answer("Faqat yaratuvchi tasdiqlaydi.", show_alert=True)
            return

    await state.clear()
    await state.set_state(WfApprovalStates.waiting_comment)
    await state.update_data(
        wfappr_step_id=step_id,
        wfappr_actor_id=actor_id,
        wfappr_action=action,
    )
    label = "tasdiqlash" if action == "ok" else "rad etish"
    prompt = (
        f"💬 <b>{label.capitalize()} sababini yozing</b>\n\n"
        f"Izoh matnini yuboring (1000 belgi gacha)."
    )
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="wfappr:cancel:0:0"),
    ]])
    try:
        await callback.message.edit_text(prompt, reply_markup=cancel_kb)
    except Exception:
        await callback.message.answer(prompt, reply_markup=cancel_kb)
    await callback.answer()


@router.message(WfApprovalStates.waiting_comment)
async def msg_wf_approval_comment(message: Message, state: FSMContext, user: User, bot: Bot):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❗ Izoh matnini yuboring yoki bekor qiling.")
        return
    if len(text) > 1000:
        await message.answer("❗ Izoh juda uzun (max 1000).")
        return

    data = await state.get_data()
    step_id = data.get("wfappr_step_id")
    actor_id = data.get("wfappr_actor_id")
    action = data.get("wfappr_action")
    if not all([step_id, actor_id, action]):
        await state.clear()
        await message.answer("❌ Xato — qadam aniqlanmadi.")
        return

    _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)

    async with get_session() as session:
        step = await session.get(TaskStep, step_id)
        if not step:
            await state.clear()
            await message.answer("❌ Qadam topilmadi.")
            return
        task = await session.get(Task, step.task_id)
        if not task:
            await state.clear()
            await message.answer("❌ Vazifa topilmadi.")
            return

        prefix = "✅ Tasdiqlandi" if action == "ok" else "❌ Rad etildi"
        session.add(TaskStepComment(
            step_id=step_id, user_id=user.id,
            content=f"{prefix}: {text}",
        ))

        if action == "ok":
            # Qadamni done qilamiz va navbatdagisini ochamiz
            step.status = "done"
            step.completed_at = datetime.now(_TZ)

            sr = await session.execute(
                select(TaskStep).where(TaskStep.task_id == step.task_id).order_by(TaskStep.order_index)
            )
            steps = list(sr.scalars())
            nxt = next((s for s in steps if s.order_index == step.order_index + 1), None)
            finished_all = False
            if nxt:
                activate_step(nxt, datetime.now(_TZ))
            else:
                task.status = TaskStatus.DONE
                task.completed_at = datetime.now(_TZ)
                finished_all = True

            await session.commit()

            # Mas'ulga xabar
            actor = await session.get(User, actor_id)
            view_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Batafsil ko'rish", callback_data=f"wf:view:{task.id}"),
            ]])
            if actor and actor.telegram_id:
                try:
                    await bot.send_message(
                        actor.telegram_id,
                        f"✅ <b>Qadamingiz tasdiqlandi!</b>\n\n"
                        f"📋 Vazifa: <b>{task.title}</b>\n"
                        f"🪜 Qadam {step.order_index+1}: <b>{step.title}</b>\n"
                        f"👤 Yaratuvchi: <b>{user.full_name}</b>\n"
                        f"💬 Izoh: <i>{text}</i>",
                        reply_markup=view_kb,
                    )
                except Exception:
                    pass

            # Keyingi qadam ijrochisiga
            if nxt:
                try:
                    nu = await session.get(User, nxt.assignee_user_id)
                    if nu and nu.telegram_id:
                        await bot.send_message(
                            nu.telegram_id,
                            f"🔔 <b>Sizning navbatingiz keldi!</b>\n\n"
                            f"📋 Vazifa #{task.id}: <b>{task.title}</b>\n"
                            f"🪜 Qadam {nxt.order_index+1}: <b>{nxt.title}</b>",
                            reply_markup=view_kb,
                        )
                except Exception:
                    pass

            await message.answer(
                f"✅ <b>Tasdiqlandi</b>\n\n"
                f"📋 Vazifa: <b>{task.title}</b>\n"
                f"🪜 Qadam: <b>{step.title}</b>\n"
                f"💬 Izoh: <i>{text}</i>"
                + ("\n\n🎉 Butun workflow yakunlandi!" if finished_all else "")
            )
        else:
            # Rad etildi — qadam yana aktivga qaytadi (muddat shu paytdan qayta hisoblanadi)
            activate_step(step, datetime.now(_TZ))
            await session.commit()

            actor = await session.get(User, actor_id)
            if actor and actor.telegram_id:
                view_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔍 Batafsil ko'rish", callback_data=f"wf:view:{task.id}"),
                ]])
                try:
                    await bot.send_message(
                        actor.telegram_id,
                        f"❌ <b>Qadamingiz rad etildi</b>\n\n"
                        f"📋 Vazifa: <b>{task.title}</b>\n"
                        f"🪜 Qadam: <b>{step.title}</b>\n"
                        f"👤 Yaratuvchi: <b>{user.full_name}</b>\n"
                        f"💬 Sabab: <i>{text}</i>\n\n"
                        f"<i>Qadam qaytadan «Aktiv» holatiga qaytdi.</i>",
                        reply_markup=view_kb,
                    )
                except Exception:
                    pass

            await message.answer(
                f"❌ <b>Rad etildi</b>\n\n"
                f"📋 Vazifa: <b>{task.title}</b>\n"
                f"🪜 Qadam: <b>{step.title}</b>\n"
                f"💬 Sabab: <i>{text}</i>"
            )

    await state.clear()
