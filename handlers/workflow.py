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
from datetime import datetime
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
    TaskStepComment, TaskStepAttachment,
)
from services.task_service import TaskService
from config import settings

router = Router()
logger = logging.getLogger(__name__)


# ─── States ──────────────────────────────────────────────────────────────────

class WorkflowStates(StatesGroup):
    waiting_title         = State()
    waiting_description   = State()
    waiting_step_title    = State()
    waiting_step_assignee = State()
    waiting_step_deadline = State()
    waiting_more_steps    = State()
    waiting_workspace     = State()
    waiting_confirm       = State()


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

async def _render_workflow_detail(task_id: int, current_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Workflow detail matni va klaviaturasini qaytaradi."""
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return "❌ Workflow topilmadi.", InlineKeyboardMarkup(inline_keyboard=[
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

        kb_rows.append([InlineKeyboardButton(
            text="➕ Subtask qo'shish",
            callback_data=f"wf:subtask:{task_id}"
        )])

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
        f"⏰ <b>Bu qadam uchun deadline (muddati)?</b>\n\n"
        f"👤 Ijrochi: <b>{member['name']}</b>\n\n"
        f"Misol: <code>{_ex_date}</code> yoki <code>{_ex_dt}</code>\n\n"
        "Deadline yo'q bo'lsa — /skip yuboring",
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


def _step_deadline_text(step: dict) -> str:
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
    dl = _parse_step_deadline(message.text)
    if not dl:
        from zoneinfo import ZoneInfo as _ZI
        _now = datetime.now(_ZI(settings.DEFAULT_TIMEZONE))
        _ex_date = _now.strftime("%d.%m.%Y")
        _ex_dt   = _now.strftime("%d.%m.%Y %H:%M")
        await message.answer(
            f"❗ Format noto'g'ri.\n"
            f"Misol: <code>{_ex_date}</code> yoki <code>{_ex_dt}</code>\n"
            "Deadline yo'q bo'lsa: /skip"
        )
        return
    await _save_step_and_continue(message, state, deadline=dl)


async def _save_step_and_continue(message: Message, state: FSMContext, deadline):
    data = await state.get_data()
    steps = data.get("steps", [])
    steps.append({
        "title": data.get("_pending_step_title", "—"),
        "assignee_id": data.get("_pending_assignee_id"),
        "assignee_name": data.get("_pending_assignee_name", "?"),
        "deadline": deadline,
    })
    await state.update_data(steps=steps, _pending_step_title=None,
                            _pending_assignee_id=None, _pending_assignee_name=None)
    await state.set_state(WorkflowStates.waiting_more_steps)

    txt = "<b>📋 Workflow qadamlari hozir:</b>\n\n"
    for i, s in enumerate(steps, 1):
        dl_txt = _step_deadline_text(s)
        txt += f"{i}. <b>{s['title']}</b>\n   👤 {s['assignee_name']}{dl_txt}\n\n"
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


@router.callback_query(WorkflowStates.waiting_more_steps, F.data == "wf:finish")
async def wf_finish(callback: CallbackQuery, state: FSMContext, user: User, bot: Bot):
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
        for i, s in enumerate(steps):
            session.add(TaskStep(
                task_id=task.id,
                order_index=i,
                title=s["title"],
                assignee_user_id=s["assignee_id"],
                status="active" if i == 0 else "pending",
                started_at=datetime.now(_TZ) if i == 0 else None,
                deadline=s.get("deadline"),
            ))
            try:
                session.add(TaskAssignment(
                    task_id=task.id, user_id=s["assignee_id"], status="new"
                ))
            except Exception:
                pass

        await session.commit()
        task_id = task.id

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
                    f"Ko'rish: /wf {task_id}\n"
                    f"Tugatgach: <code>/done {task_id}</code>",
                )
        except Exception as e:
            logger.warning(f"Workflow notify xato: {e}")

    _TZ_sum = ZoneInfo(settings.DEFAULT_TIMEZONE)
    summary = f"✅ <b>Workflow vazifa yaratildi!</b>\n\n📋 {title}\n\n<b>Qadamlar:</b>\n"
    for i, s in enumerate(steps, 1):
        marker = "🟢" if i == 1 else "⚪"
        dl = s.get("deadline")
        dl_txt = f" | ⏰ {dl.astimezone(_TZ_sum).strftime('%d.%m.%Y %H:%M')}" if dl else ""
        summary += f"{marker} {i}. {s['title']} — 👤 {s['assignee_name']}{dl_txt}\n"
    summary += f"\n💡 Birinchi ijrochiga bildirishnoma yuborildi."

    await callback.message.edit_text(
        summary,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Workflow ko'rish", callback_data=f"wf:view:{task_id}")],
            [InlineKeyboardButton(text="➕ Subtask qo'shish",  callback_data=f"wf:subtask:{task_id}")],
        ])
    )
    await callback.answer("Tayyor!")
    await state.clear()


@router.callback_query(F.data == "wf:cancel")
async def wf_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Workflow yaratish bekor qilindi.")
    await callback.answer()


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
        await callback.message.answer("❌ Bekor qilindi.")
    await callback.answer()


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
        cur.status       = status
        cur.completed_at = datetime.now(_TZ) if status == "done" else None

        sr = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.order_index)
        )
        steps = list(sr.scalars())
        nxt   = next((s for s in steps if s.order_index == cur.order_index + 1), None)

        finished_all = False
        if status == "done" and nxt:
            nxt.status     = "active"
            nxt.started_at = datetime.now(_TZ)
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
