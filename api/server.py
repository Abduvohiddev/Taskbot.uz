"""
Mini App uchun API server (aiohttp)
Static fayllar + REST API
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from aiohttp import web
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from api.auth import validate_init_data, validate_auth_token
from config import settings
from database.db import get_session
from database.models import (
    User, Task, TaskStatus, Priority, TaskAssignment,
    TaskHistory, TaskComment, TaskAttachment, GroupMember, Company, CompanyMember, CompanyRole,
    TaskStep, TaskStepComment, TaskStepAttachment, Group,
    HRDocument, HRAssignment, HRAssignmentStatus,
    Feedback, FeedbackAttachment, FeedbackReply, FeedbackType, FeedbackStatus,
    FeedbackDiscussion, Reminder,
)
from services.notification_service import NotificationService
from services.ai_service import AIService

logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
_TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
_UTC = ZoneInfo("UTC")

# ===== Admin credentials =====
_ADMIN_USERNAME = "admin4454"
_ADMIN_PASSWORD = "abduvohid4454"
_ADMIN_SECRET   = "taskbot_admin_panel_secret_2026"

# Admin panelga kira oladigan barcha hisoblar (login: parol)
_ADMIN_ACCOUNTS = {
    "admin4454": "abduvohid4454",
    "hradmin":   "hr1234",
}

def _admin_token_for(username: str, password: str) -> str:
    return hashlib.sha256(f"{username}:{password}:{_ADMIN_SECRET}".encode()).hexdigest()

# Har bir hisob uchun token — tekshiruvda shu to'plamdan biriga mos kelsa yetarli
_ADMIN_TOKENS = { _admin_token_for(u, p) for u, p in _ADMIN_ACCOUNTS.items() }
# Backward-compat: asosiy token
_ADMIN_TOKEN = _admin_token_for(_ADMIN_USERNAME, _ADMIN_PASSWORD)

# ===== HR credentials =====
_HR_USERNAME = "hradmin"
_HR_PASSWORD = "hr1234"
_HR_SECRET   = "taskbot_hr_panel_secret_2026"
_HR_TOKEN    = hashlib.sha256(
    f"{_HR_USERNAME}:{_HR_PASSWORD}:{_HR_SECRET}".encode()
).hexdigest()

HR_UPLOADS_DIR = Path(__file__).parent.parent / "hr_uploads"
HR_UPLOADS_DIR.mkdir(exist_ok=True)


# ===== Middleware =====

@web.middleware
async def cors_middleware(request, handler):
    """CORS headers for all responses"""
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as ex:
            resp = ex
    
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data, X-Auth-Token"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return resp


@web.middleware
async def auth_middleware(request, handler):
    """Authenticate user from Telegram initData"""
    # Skip auth for static files and admin API routes
    if not request.path.startswith("/api"):
        return await handler(request)
    if request.path.startswith("/admin/api"):
        return await handler(request)
    if request.path.startswith("/hr/api"):
        return await handler(request)
    
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_info = validate_init_data(init_data) if init_data else None

    # Fallback: token-based auth (Telegram Desktop uchun)
    if not user_info:
        auth_token = request.headers.get("X-Auth-Token", "")
        if auth_token:
            user_info = validate_auth_token(auth_token)

    if not user_info:
        logger.warning(
            "Auth failed — initData: %s, token: %s",
            "present" if init_data else "empty",
            "present" if request.headers.get("X-Auth-Token") else "empty",
        )
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "Autentifikatsiya talab qilinadi"}),
            content_type="application/json",
        )
    
    request["user_telegram_id"] = user_info["telegram_id"]
    return await handler(request)


async def get_user_from_request(request) -> User | None:
    """Request dan foydalanuvchini topish"""
    tg_id = request.get("user_telegram_id")
    if not tg_id:
        return None
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_id)
        )
        return result.scalar_one_or_none()


# ===== API Routes =====

async def api_get_tasks(request):
    """Foydalanuvchi vazifalari"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    async with get_session() as session:
        company_id_str = request.query.get("company_id")
        from sqlalchemy import or_

        # MUHIM: TaskAssignment ga outerjoin ishlatmaymiz — chunki user filtrlash
        # uchun exists() subquerylar bor, va outer join SQLAlchemy auto-correlation
        # muammosini keltirib chiqaradi.
        stmt = select(Task)

        if company_id_str == "all":
            # "Hammasi" — uchta manbadan birlashtirib ko'rsatamiz:
            #   1) SHAXSIY: company yo'q, group yo'q — user creator yoki assignee
            #   2) JAMOA: user a'zo bo'lgan kompaniyaning BARCHA tasklari
            #   3) GURUH: user bevosita a'zo bo'lgan guruhlarning BARCHA tasklari
            member_cos = await session.execute(
                select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
            )
            company_ids = [c[0] for c in member_cos.all()]
            member_grps = await session.execute(
                select(GroupMember.group_id).where(GroupMember.user_id == user.id)
            )
            user_group_ids = [g[0] for g in member_grps.all()]

            from sqlalchemy import exists, select as _sel
            from sqlalchemy.orm import aliased
            _TA = aliased(TaskAssignment)
            has_any_asg = exists(_sel(_TA.id).where(
                _TA.task_id == Task.id, _TA.user_id == user.id,
            ))

            visibility_parts = [
                # 1) Shaxsiy — faqat user ishtirok etgan bo'lsa
                and_(
                    Task.company_id.is_(None),
                    Task.group_id.is_(None),
                    or_(Task.creator_id == user.id, has_any_asg),
                ),
            ]
            # 2) Kompaniya tasklari — barchasi
            if company_ids:
                visibility_parts.append(Task.company_id.in_(company_ids))
            # 3) Guruh tasklari — barchasi
            if user_group_ids:
                visibility_parts.append(Task.group_id.in_(user_group_ids))

            stmt = stmt.where(or_(*visibility_parts))
        elif company_id_str and company_id_str != "personal":
            company_id = int(company_id_str)
            # Faqat kompaniya a'zolari ko'ra oladi
            member_check = await session.execute(
                select(CompanyMember).where(
                    and_(
                        CompanyMember.company_id == company_id,
                        CompanyMember.user_id == user.id,
                    )
                )
            )
            if not member_check.scalar_one_or_none():
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "Bu kompaniya a'zosi emassiz"}),
                    content_type="application/json",
                )
            # Kompaniya tasklari + shu kompaniyaga bog'liq guruh tasklari
            grp_res = await session.execute(
                select(Group.id).where(Group.company_id == company_id)
            )
            group_ids = [g[0] for g in grp_res.all()]
            co_cond = [Task.company_id == company_id]
            if group_ids:
                co_cond.append(Task.group_id.in_(group_ids))
            stmt = stmt.where(or_(*co_cond))
        elif company_id_str == "personal":
            # Shaxsiy view ham keng — foydalanuvchi har qanday rolda ishtirok etgan
            # shaxsiy tasklarni ko'rsatamiz.
            from sqlalchemy import exists, select as _sel
            from sqlalchemy.orm import aliased
            _TA = aliased(TaskAssignment)
            has_any_asg = exists(_sel(_TA.id).where(
                _TA.task_id == Task.id, _TA.user_id == user.id,
            ))
            stmt = stmt.where(
                Task.company_id.is_(None),
                Task.group_id.is_(None),
            ).where(or_(Task.creator_id == user.id, has_any_asg))
        # No filter — show all tasks

        result = await session.execute(
            stmt.options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.subtasks),
                selectinload(Task.steps),
            )
            .order_by(Task.created_at.desc())
            .distinct()
        )
        tasks = list(result.scalars().unique().all())
    
    tasks_json = [_task_to_dict(t) for t in tasks]
    
    return web.json_response({
        "tasks": tasks_json,
        "user_name": user.full_name,
        "user_id": user.id,
        "total": len(tasks_json),
    })


async def api_get_task_tree(request):
    """Vazifaning to'liq rekursiv tree'si — Mind Map uchun.
    Har subtask uchun: status, mas'ullar, izoh/fayl soni, ichki subtasklar."""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    MAX_DEPTH = 8

    async def _build(tid, depth):
        res = await session.execute(
            select(Task).where(Task.id == tid).options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.subtasks),
            )
        )
        t = res.scalar_one_or_none()
        if not t:
            return None

        # izoh / fayl soni
        cmt_n = (await session.execute(
            select(func.count(TaskComment.id)).where(TaskComment.task_id == tid)
        )).scalar() or 0
        att_n = (await session.execute(
            select(func.count(TaskAttachment.id)).where(TaskAttachment.task_id == tid)
        )).scalar() or 0
        # workflow qadam soni
        step_n = (await session.execute(
            select(func.count(TaskStep.id)).where(TaskStep.task_id == tid)
        )).scalar() or 0

        node = {
            "id": t.id,
            "title": t.title,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "priority": t.priority.value if hasattr(t.priority, "value") else str(t.priority),
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "creator_name": t.creator.full_name if t.creator else None,
            "comments_count": int(cmt_n),
            "attachments_count": int(att_n),
            "has_workflow": step_n > 0,
            "assignees": [
                {
                    "name": a.user.full_name if a.user else "—",
                    "status": a.status.value if hasattr(a.status, "value") else (a.status or "new"),
                    "is_responsible": bool(a.is_responsible),
                    "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                }
                for a in (t.assignments or [])
            ],
            "subtasks": [],
        }

        if depth < MAX_DEPTH:
            child_ids = [s.id for s in (t.subtasks or [])]
            for cid in child_ids:
                child = await _build(cid, depth + 1)
                if child:
                    node["subtasks"].append(child)
        return node

    async with get_session() as session:
        root_check = await session.execute(select(Task).where(Task.id == task_id))
        if not root_check.scalar_one_or_none():
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )
        tree = await _build(task_id, 0)
    return web.json_response({"ok": True, "tree": tree})


async def api_get_task(request):
    """Bitta vazifa tafsilotlari + tarix (roadmap)"""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    async with get_session() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.attachments),
                selectinload(Task.subtasks),
            )
        )
        task = result.scalar_one_or_none()

        if not task:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )

        if not await _user_can_access_task(session, user, task):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Ruxsat yo'q"}),
                content_type="application/json",
            )

        hist_res = await session.execute(
            select(TaskHistory, User)
            .join(User, User.id == TaskHistory.user_id, isouter=True)
            .where(TaskHistory.task_id == task_id)
            .order_by(TaskHistory.created_at.asc())
        )
        history = []
        for h, u in hist_res.all():
            history.append({
                "id": h.id,
                "type": "history",
                "action": h.action,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "user_name": u.full_name if u else None,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            })

        comm_res = await session.execute(
            select(TaskComment, User)
            .join(User, User.id == TaskComment.user_id, isouter=True)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        )
        for c, u in comm_res.all():
            history.append({
                "id": f"c{c.id}",
                "type": "comment",
                "action": "comment",
                "content": c.content,
                "user_name": u.full_name if u else "Noma'lum",
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })
        history.sort(key=lambda x: x["created_at"] or "")

        task_dict = _task_to_dict(task)
        task_dict["is_creator"] = (task.creator_id == user.id)
        my_assignment = next((a for a in (task.assignments or []) if a.user_id == user.id), None)
        task_dict["my_status"] = (
            (my_assignment.status.value if hasattr(my_assignment.status, "value") else (my_assignment.status or "new"))
            if my_assignment else None
        )
        task_dict["my_is_responsible"] = bool(my_assignment.is_responsible) if my_assignment else False
        task_dict["my_role"] = "responsible" if (my_assignment and my_assignment.is_responsible) else ("observer" if my_assignment else None)

        # Check if task has workflow steps
        steps_res = await session.execute(
            select(func.count()).select_from(TaskStep)
            .where(TaskStep.task_id == task_id)
        )
        steps_count = int(steps_res.scalar() or 0)
        task_dict["has_workflow"] = steps_count > 0

        task_dict["history"] = history

    return web.json_response({"task": task_dict})


async def api_add_comment(request):
    """Vazifaga izoh qo'shish"""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    content = (body.get("content") or "").strip()
    if not content or len(content) > 1000:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Izoh 1-1000 belgi bo'lsin"}))

    recipient_ids = set()
    async with get_session() as session:
        task_res = await session.execute(
            select(Task).where(Task.id == task_id)
            .options(selectinload(Task.assignments))
        )
        task = task_res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(text=json.dumps({"error": "Vazifa topilmadi"}),
                                   content_type="application/json")

        if not await _user_can_access_task(session, user, task):
            raise web.HTTPForbidden(text=json.dumps({"error": "Ruxsat yo'q"}),
                                    content_type="application/json")

        comment = TaskComment(task_id=task_id, user_id=user.id, content=content)
        session.add(comment)

        recipient_ids.add(task.creator_id)
        for a in task.assignments:
            recipient_ids.add(a.user_id)
        await session.flush()
        comment_id = comment.id
        await session.commit()

    bot = request.app.get("bot")
    if bot:
        # Shaxsiy xabar — comment yozgandan boshqalarga
        notify_ids = recipient_ids - {user.id}
        if notify_ids:
            try:
                async with get_session() as ns:
                    await NotificationService.notify_new_comment(
                        bot, ns, task, user.full_name, content,
                        recipient_ids=notify_ids,
                    )
            except Exception as e:
                logger.warning(f"Comment personal notification xatosi: {e}")

        # Guruh chatiga izoh xabari
        try:
            async with get_session() as gs:
                grp_tg_id = await _get_task_group_tg_id(gs, task)
                if grp_tg_id:
                    preview = content[:120] + "…" if len(content) > 120 else content
                    group_msg = (
                        f"💬 <b>Yangi izoh</b>\n\n"
                        f"📌 <b>{task.title}</b>\n"
                        f"👤 <b>{user.full_name}:</b>\n"
                        f"{preview}"
                    )
                    try:
                        await bot.send_message(
                            chat_id=grp_tg_id, text=group_msg, parse_mode="HTML"
                        )
                    except Exception as ex:
                        logger.warning(f"Guruh comment xabari yuborib bo'lmadi {grp_tg_id}: {ex}")
        except Exception as e:
            logger.warning(f"Comment guruh notification xatosi: {e}")

    return web.json_response({
        "ok": True,
        "comment": {
            "id": f"c{comment_id}",
            "type": "comment",
            "action": "comment",
            "content": content,
            "user_name": user.full_name,
            "created_at": datetime.now(_TZ).strftime("%d.%m.%Y %H:%M"),
        }
    }, status=201)


def _compute_task_status(assignments, old_status):
    """Vazifaning umumiy statusini ijrochilar statuslari asosida hisoblaydi.

    MUHIM: Bot logikasi (check_and_auto_complete) bilan bir xil — vazifa
    DONE bo'lishi uchun FAQAT masul (is_responsible) ijrochilar 'done' bo'lishi
    kerak. Ishtirokchilar (observer) hisobga olinmaydi. Masul yo'q bo'lsa —
    barcha ijrochilar hisobga olinadi.
    """
    if not assignments:
        return old_status

    resp = [a for a in assignments if a.is_responsible]
    if not resp:
        resp = assignments  # masul belgilanmagan — hammasi hisoblanadi

    resp_statuses = [(a.status or "new") for a in resp]
    all_statuses = [(a.status or "new") for a in assignments]

    if resp_statuses and all(s == "done" for s in resp_statuses):
        return TaskStatus.DONE
    if any(s == "in_progress" for s in all_statuses):
        return TaskStatus.IN_PROGRESS
    if any(s == "review" for s in all_statuses):
        return TaskStatus.REVIEW
    if all_statuses and all(s in ("new", "cancelled") for s in all_statuses):
        return TaskStatus.NEW
    return old_status


async def api_update_my_status(request):
    """Faqat joriy foydalanuvchi o'z assignment statusini yangilaydi.
    Masul (responsible) ijrochilar DONE bo'lganda Task umumiy statusi DONE bo'ladi.
    """
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    try:
        new_status = TaskStatus(body.get("status"))
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Noto'g'ri status"}))

    async with get_session() as session:
        a_res = await session.execute(
            select(TaskAssignment).where(
                and_(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.user_id == user.id,
                )
            )
        )
        assignment = a_res.scalar_one_or_none()
        if not assignment:
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Siz bu vazifa ijrochisi emassiz"}),
                content_type="application/json",
            )
        # Har qanday ijrochi o'z shaxsiy statusini o'zgartira oladi

        old_my = assignment.status or "new"

        # ── Yaratuvchi tasdig'i — agar mas'ul "done" qilmoqchi bo'lsa,
        # avval yaratuvchidan ruxsat so'raymiz (creator bo'lmasa)
        task_for_creator = (await session.execute(
            select(Task).where(Task.id == task_id)
        )).scalar_one()
        needs_approval = (
            new_status == TaskStatus.DONE
            and assignment.is_responsible
            and user.id != task_for_creator.creator_id
        )
        if needs_approval:
            # "review" — yaratuvchi tasdiqlashini kutmoqda
            assignment.status = "review"
        else:
            assignment.status = new_status.value

        # ── Vaqt kuzatuvi ────────────────────────────────────────────────────
        _now_utc = datetime.now(_UTC)
        if new_status == TaskStatus.IN_PROGRESS and not assignment.started_at:
            # Jarayonga tushganda taymer boshlanadi (faqat bir marta)
            assignment.started_at = _now_utc
        if (not needs_approval) and new_status == TaskStatus.DONE:
            assignment.completed_at = _now_utc
            if assignment.started_at:
                assignment.duration_seconds = int(
                    (_now_utc - assignment.started_at).total_seconds()
                )
        elif new_status != TaskStatus.DONE:
            assignment.completed_at = None

        session.add(TaskHistory(
            task_id=task_id,
            user_id=user.id,
            action="my_status_changed",
            old_value={"status": old_my, "user_name": user.full_name},
            new_value={"status": new_status.value, "user_name": user.full_name},
        ))

        # Ixtiyoriy izoh — status o'zgarishi bilan birga
        comment_text = (body.get("comment") or "").strip()[:500]
        if comment_text:
            session.add(TaskComment(
                task_id=task_id, user_id=user.id,
                content=comment_text,
            ))

        task_res = await session.execute(
            select(Task).where(Task.id == task_id)
            .options(selectinload(Task.assignments))
        )
        task = task_res.scalar_one()
        old_task_status = task.status

        assignments = task.assignments or []
        new_task_status = _compute_task_status(assignments, old_task_status)

        if new_task_status != old_task_status:
            task.status = new_task_status
            if new_task_status == TaskStatus.DONE:
                task.completed_at = datetime.now(_UTC)
            session.add(TaskHistory(
                task_id=task_id,
                user_id=user.id,
                action="status_changed",
                old_value={"status": old_task_status.value},
                new_value={"status": new_task_status.value},
            ))

        # Commit oldidan recipient ID'larni yig'amiz
        recipient_ids = {task.creator_id}
        for a in assignments:
            recipient_ids.add(a.user_id)

        await session.commit()

    # Yangi session bilan notification
    bot = request.app.get("bot")
    if bot:
        try:
            async with get_session() as ns:
                # Har doim har bir assigneega xabar (my_status o'zgardi)
                await NotificationService.notify_my_status_changed(
                    bot, ns, task,
                    new_status.value, user.full_name,
                    recipient_ids=recipient_ids,
                )
                # Umumiy task status o'zgarganda qo'shimcha xabar
                if new_task_status != old_task_status:
                    await NotificationService.notify_status_changed(
                        bot, ns, task,
                        old_task_status.value, new_task_status.value, user.full_name,
                        recipient_ids=recipient_ids,
                    )
        except Exception as e:
            logger.warning(f"My-status notification xatosi: {e}")

        # Guruh chatiga status o'zgarishi
        try:
            async with get_session() as gs:
                grp_tg_id = await _get_task_group_tg_id(gs, task)
                if grp_tg_id:
                    status_label = new_task_status.value if new_task_status != old_task_status else new_status.value
                    old_lbl = old_task_status.value if new_task_status != old_task_status else (old_my or "new")
                    await NotificationService.notify_group_status_changed(
                        bot, grp_tg_id, task, old_lbl, status_label, user.full_name
                    )
        except Exception as e:
            logger.warning(f"Guruh my-status notification xatosi: {e}")

    # Yaratuvchiga tasdiqlash so'rovi yuborish
    if needs_approval and bot:
        try:
            async with get_session() as ns:
                tk = await ns.get(Task, task_id)
                creator = await ns.get(User, tk.creator_id) if tk else None
                if creator and creator.telegram_id:
                    from aiogram.types import (
                        InlineKeyboardButton as _IKB,
                        InlineKeyboardMarkup as _IKM,
                    )
                    kb = _IKM(inline_keyboard=[[
                        _IKB(text="✅ Tasdiqlash", callback_data=f"appr:ok:{task_id}:{user.id}"),
                        _IKB(text="❌ Rad etish",  callback_data=f"appr:no:{task_id}:{user.id}"),
                    ]])
                    desc = f"\n📝 {tk.description[:200]}" if tk.description else ""
                    msg = (
                        f"⏳ <b>Vazifa tasdiqlash kutilmoqda</b>\n\n"
                        f"📋 <b>{tk.title}</b>{desc}\n\n"
                        f"👤 <b>{user.full_name}</b> bu vazifani "
                        f"<b>«Bajarildi»</b> deb belgilamoqchi.\n"
                        f"Tasdiqlaysizmi?"
                    )
                    await bot.send_message(
                        creator.telegram_id, msg, reply_markup=kb,
                    )
        except Exception as e:
            logger.warning(f"Tasdiqlash so'rovi xato: {e}")

    return web.json_response({
        "ok": True,
        "my_status": ("review" if needs_approval else new_status.value),
        "task_status": new_task_status.value,
        "pending_approval": needs_approval,
        "message": (
            "⏳ Vazifa yaratuvchidan tasdiqlash kutmoqda" if needs_approval else None
        ),
    })


async def _user_can_access_task(session, user: User, task: Task) -> bool:
    """Barcha foydalanuvchilar barcha vazifalarga kira oladi"""
    return True


async def _get_task_group_tg_id(session, task: Task) -> Optional[int]:
    """Vazifaning telegram guruh ID sini qaytaradi (group_id → company_id tartibida)"""
    # 1. Vazifa to'g'ridan-to'g'ri guruhga biriktirilgan bo'lsa
    if task.group_id:
        grp_res = await session.execute(
            select(Group).where(Group.id == task.group_id)
        )
        grp = grp_res.scalar_one_or_none()
        if grp and grp.telegram_group_id:
            return grp.telegram_group_id

    # 2. Kompaniya guruhi orqali
    if task.company_id:
        grp_res = await session.execute(
            select(Group).where(
                Group.company_id == task.company_id,
                Group.telegram_group_id.isnot(None),
                Group.is_active == True,
            ).limit(1)
        )
        grp = grp_res.scalar_one_or_none()
        if grp and grp.telegram_group_id:
            return grp.telegram_group_id

    return None


async def api_create_task(request):
    """Yangi vazifa yaratish"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    title = body.get("title", "").strip()
    if not title or len(title) < 3:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Nom kamida 3 belgi"}))

    description = body.get("description")
    priority_str = body.get("priority", "medium")
    deadline_str = body.get("deadline")
    company_id_str = body.get("company_id")
    assignee_ids_raw = body.get("assignee_ids") or []
    responsible_id_raw = body.get("responsible_user_id") or body.get("responsible_id")
    responsible_ids_raw = body.get("responsible_ids") or []  # Multiple responsible support

    try:
        priority = Priority(priority_str)
    except ValueError:
        priority = Priority.MEDIUM

    deadline = None
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            # timezone info saqlash — PostgreSQL TZ=Asia/Tashkent uchun muhim
        except (ValueError, TypeError):
            pass

    async with get_session() as session:
        c_id = None
        if company_id_str and company_id_str != "personal":
            c_id = int(company_id_str)
            member_check = await session.execute(
                select(CompanyMember).where(
                    and_(
                        CompanyMember.company_id == c_id,
                        CompanyMember.user_id == user.id,
                    )
                )
            )
            if not member_check.scalar_one_or_none():
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "Bu kompaniya a'zosi emassiz"}),
                    content_type="application/json",
                )

        # Ijrochilarni tekshirish — User jadvalida mavjud bo'lishi yetarli
        try:
            assignee_ids = [int(x) for x in assignee_ids_raw if x]
        except (ValueError, TypeError):
            assignee_ids = []

        if assignee_ids:
            # Faqat users jadvalida mavjud user_id larni qabul qilamiz
            # (boshqa kompaniyadan qo'shilgan a'zolar ham tanlana oladi)
            valid_res = await session.execute(
                select(User.id).where(User.id.in_(assignee_ids))
            )
            valid_ids = {row[0] for row in valid_res.all()}
            assignee_ids = [uid for uid in assignee_ids if uid in valid_ids]

        if not assignee_ids:
            assignee_ids = [user.id]

        parent_id = body.get("parent_id")
        try:
            parent_id = int(parent_id) if parent_id else None
        except (ValueError, TypeError):
            parent_id = None

        task = Task(
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            creator_id=user.id,
            company_id=c_id,
            parent_id=parent_id,
            status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()

        try:
            resp_id = int(responsible_id_raw) if responsible_id_raw else None
        except (ValueError, TypeError):
            resp_id = None

        # Build set of responsible user IDs (multiple responsible support)
        try:
            resp_ids_list = [int(x) for x in responsible_ids_raw if x]
        except (ValueError, TypeError):
            resp_ids_list = []

        if resp_ids_list:
            resp_ids_set = set(resp_ids_list)
        elif resp_id:
            resp_ids_set = {resp_id}
        elif len(assignee_ids) == 1:
            resp_ids_set = {assignee_ids[0]}
        else:
            resp_ids_set = set()

        for uid in assignee_ids:
            is_resp = uid in resp_ids_set
            session.add(TaskAssignment(task_id=task.id, user_id=uid, is_responsible=is_resp))

        history = TaskHistory(
            task_id=task.id,
            user_id=user.id,
            action="created",
            new_value={"title": title, "priority": priority_str},
        )
        session.add(history)

        # Subtask bo'lsa — parent taskga ham history yozamiz
        if parent_id:
            session.add(TaskHistory(
                task_id=parent_id,
                user_id=user.id,
                action="subtask_created",
                new_value={"subtask_id": task.id, "subtask_title": title},
            ))

        await session.flush()

        result = await session.execute(
            select(Task)
            .where(Task.id == task.id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.subtasks),
            )
        )
        task = result.scalar_one()
        # MUHIM: barcha ijrochilarni xabarnoma ro'yxatiga qo'shamiz (creator dan boshqa)
        notify_ids = [uid for uid in assignee_ids if uid != user.id]
        task_id_for_notify = task.id
        task_dict = _task_to_dict(task)
        task_for_notify = task
        # responsible_id ni ham saqlaymiz
        notify_resp_id = resp_id
        await session.commit()

    # Yangi session bilan notification — masul shaxs uchun maxsus xabar
    bot = request.app.get("bot")
    if bot:
        if notify_ids:
            try:
                async with get_session() as ns:
                    await NotificationService.notify_task_assigned(
                        bot, ns, task_for_notify, notify_ids,
                        responsible_user_ids=list(resp_ids_set) if resp_ids_set else None,
                    )
            except Exception as e:
                logger.warning(f"Notification xatosi: {e}")

        # Guruh chatiga notification
        if c_id:
            try:
                async with get_session() as gs:
                    grp_res = await gs.execute(
                        select(Group).where(
                            Group.company_id == c_id,
                            Group.is_active == True,
                        )
                    )
                    grp = grp_res.scalar_one_or_none()
                    if grp and grp.telegram_group_id:
                        await NotificationService.notify_group_task_created(
                            bot, grp.telegram_group_id, task_for_notify
                        )
            except Exception as e:
                logger.warning(f"Guruh task notification xatosi: {e}")

    return web.json_response({"task": task_dict, "ok": True}, status=201)


async def api_get_company_members(request):
    """Kompaniya a'zolari ro'yxati (ijrochi tanlash uchun)"""
    company_id = int(request.match_info["company_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    async with get_session() as session:
        member_check = await session.execute(
            select(CompanyMember).where(
                and_(
                    CompanyMember.company_id == company_id,
                    CompanyMember.user_id == user.id,
                )
            )
        )
        if not member_check.scalar_one_or_none():
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Bu kompaniya a'zosi emassiz"}),
                content_type="application/json",
            )

        result = await session.execute(
            select(CompanyMember)
            .where(CompanyMember.company_id == company_id)
            .options(selectinload(CompanyMember.user))
            .order_by(CompanyMember.role, CompanyMember.joined_at)
        )
        members = list(result.scalars().all())

    data = [
        {
            "id": m.user.id,
            "name": m.user.full_name,
            "username": m.user.username,
            "role": m.role.value,
            "is_self": m.user.id == user.id,
        }
        for m in members
    ]
    return web.json_response({"members": data})


async def api_update_status(request):
    """Vazifa statusini yangilash"""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))
    
    new_status_str = body.get("status")
    try:
        new_status = TaskStatus(new_status_str)
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Noto'g'ri status"}))
    
    async with get_session() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.attachments),
                selectinload(Task.subtasks),
            )
        )
        task = result.scalar_one_or_none()

        if not task:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )

        if not await _user_can_access_task(session, user, task):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Ruxsat yo'q"}),
                content_type="application/json",
            )

        old_status = task.status
        task.status = new_status

        if new_status == TaskStatus.DONE:
            task.completed_at = datetime.now(_UTC)

        session.add(TaskHistory(
            task_id=task_id,
            user_id=user.id,
            action="status_changed",
            old_value={"status": old_status.value},
            new_value={"status": new_status.value},
        ))

        # Commit oldidan recipient ID'larni yig'amiz
        recipient_ids = {task.creator_id}
        for a in task.assignments:
            recipient_ids.add(a.user_id)

        await session.commit()

    # Yangi session bilan notification
    bot = request.app.get("bot")
    if bot:
        try:
            async with get_session() as ns:
                await NotificationService.notify_status_changed(
                    bot, ns, task,
                    old_status.value, new_status.value, user.full_name,
                    recipient_ids=recipient_ids,
                )
        except Exception as e:
            logger.warning(f"Status notification xatosi: {e}")

        # Guruh chatiga status o'zgarishi
        try:
            async with get_session() as gs:
                grp_tg_id = await _get_task_group_tg_id(gs, task)
                if grp_tg_id:
                    await NotificationService.notify_group_status_changed(
                        bot, grp_tg_id, task,
                        old_status.value, new_status.value, user.full_name
                    )
        except Exception as e:
            logger.warning(f"Guruh status notification xatosi: {e}")

    return web.json_response({"ok": True, "status": new_status.value})


async def api_get_stats(request):
    """Foydalanuvchi statistikasi. CEO uchun member_id filter qo'shildi."""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    is_admin = False
    is_company = False
    member_name = None
    async with get_session() as session:
        company_id_str = request.query.get("company_id")
        member_id_str = request.query.get("member_id")   # CEO filter: specific member
        from sqlalchemy import or_

        # MUHIM: outerjoin(TaskAssignment) ishlatmaymiz — har task har bir
        # assignment uchun takror sanaladi (kartesian). Faqat member_id filter
        # kerak bo'lganda join qo'shamiz.
        stmt = select(Task.status, func.count(Task.id))

        if company_id_str == "all":
            # "Hammasi" stats — shaxsiy ishtirok + jamoa/guruh tasklari
            member_cos = await session.execute(
                select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
            )
            company_ids = [c[0] for c in member_cos.all()]
            member_grps = await session.execute(
                select(GroupMember.group_id).where(GroupMember.user_id == user.id)
            )
            user_group_ids = [g[0] for g in member_grps.all()]

            from sqlalchemy import exists, select as _sel
            from sqlalchemy.orm import aliased
            _TA = aliased(TaskAssignment)
            has_any_asg = exists(_sel(_TA.id).where(
                _TA.task_id == Task.id, _TA.user_id == user.id,
            ))

            visibility_parts = [
                and_(
                    Task.company_id.is_(None),
                    Task.group_id.is_(None),
                    or_(Task.creator_id == user.id, has_any_asg),
                ),
            ]
            if company_ids:
                visibility_parts.append(Task.company_id.in_(company_ids))
            if user_group_ids:
                visibility_parts.append(Task.group_id.in_(user_group_ids))

            stmt = stmt.where(or_(*visibility_parts))
        elif company_id_str and company_id_str != "personal":
            is_company = True
            company_id = int(company_id_str)
            member_check = await session.execute(
                select(CompanyMember).where(
                    and_(CompanyMember.company_id == company_id, CompanyMember.user_id == user.id)
                )
            )
            member = member_check.scalar_one_or_none()
            if not member:
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "Bu jamoa a'zosi emassiz"}),
                    content_type="application/json",
                )
            is_admin = member.role in (CompanyRole.OWNER, CompanyRole.ADMIN)
            stmt = stmt.where(Task.company_id == company_id)
            # CEO member_id filter — bu joyda join kerak, lekin DISTINCT bilan
            # duplicates oldini olamiz (1 user 1 vazifaga 1 marta biriktirilgan,
            # shuning uchun bu yerda kartesian xavfi yo'q).
            if member_id_str and is_admin:
                target_uid = int(member_id_str)
                stmt = (
                    stmt.join(TaskAssignment, TaskAssignment.task_id == Task.id)
                        .where(TaskAssignment.user_id == target_uid)
                )
                # member ismini yuklaymiz
                usr_res = await session.execute(select(User).where(User.id == target_uid))
                target_usr = usr_res.scalar_one_or_none()
                if target_usr:
                    member_name = target_usr.full_name
        elif company_id_str == "personal":
            from sqlalchemy import exists, select as _sel
            from sqlalchemy.orm import aliased
            _TA1 = aliased(TaskAssignment)
            _TA2 = aliased(TaskAssignment)
            has_resp_asg = exists(_sel(_TA1.id).where(
                _TA1.task_id == Task.id, _TA1.user_id == user.id, _TA1.is_responsible == True,
            ))
            has_any_asg = exists(_sel(_TA2.id).where(
                _TA2.task_id == Task.id, _TA2.user_id == user.id,
            ))
            stmt = stmt.where(Task.company_id.is_(None)).where(
                or_(has_resp_asg, and_(Task.creator_id == user.id, ~has_any_asg))
            )
        else:
            from sqlalchemy import exists, select as _sel
            from sqlalchemy.orm import aliased
            _TA1 = aliased(TaskAssignment)
            _TA2 = aliased(TaskAssignment)
            has_resp_asg = exists(_sel(_TA1.id).where(
                _TA1.task_id == Task.id, _TA1.user_id == user.id, _TA1.is_responsible == True,
            ))
            has_any_asg = exists(_sel(_TA2.id).where(
                _TA2.task_id == Task.id, _TA2.user_id == user.id,
            ))
            stmt = stmt.where(
                or_(has_resp_asg, and_(Task.creator_id == user.id, ~has_any_asg))
            )

        result = await session.execute(stmt.group_by(Task.status))
        status_counts = {row[0].value: row[1] for row in result.all()}

        # Kechikib bajarilgan tasklar — alohida hisoblaymiz va overdue ga qo'shamiz
        # (eski "stmt" filtrlarini saqlash uchun whereclause'ini olib qaytadan ishlatamiz)
        late_done_stmt = (
            select(func.count(Task.id.distinct()))
            .where(
                Task.status == TaskStatus.DONE,
                Task.completed_at.isnot(None),
                Task.deadline.isnot(None),
                Task.completed_at > Task.deadline,
            )
        )
        # Asl stmt'ning visibility shartlarini qaytadan tutamiz —
        # eng oson yo'l: stmt obyektidan WHERE clause'larni ko'chiramiz
        try:
            wc = stmt.whereclause
            if wc is not None:
                late_done_stmt = late_done_stmt.where(wc)
        except Exception:
            pass
        late_done_count = (await session.execute(late_done_stmt)).scalar() or 0

        # ── SHAXSIY kechikkanlar ──
        # Kechikkan KPI faqat foydalanuvchining MAS'UL bo'lgan vazifalarini sanaydi.
        # Kuzatuvchi yoki creator-only bo'lganlar hisobga olinmaydi.
        target_uid_for_overdue = user.id
        if member_id_str and is_admin:
            try:
                target_uid_for_overdue = int(member_id_str)
            except Exception:
                pass
        my_overdue_active = (await session.execute(
            select(func.count(Task.id.distinct()))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.user_id == target_uid_for_overdue,
                TaskAssignment.is_responsible.is_(True),
                Task.status == TaskStatus.OVERDUE,
            )
        )).scalar() or 0
        my_late_done = (await session.execute(
            select(func.count(Task.id.distinct()))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.user_id == target_uid_for_overdue,
                TaskAssignment.is_responsible.is_(True),
                Task.status == TaskStatus.DONE,
                Task.completed_at.isnot(None),
                Task.deadline.isnot(None),
                Task.completed_at > Task.deadline,
            )
        )).scalar() or 0
        my_overdue_total = my_overdue_active + my_late_done

        employee_stats = []
        if company_id_str and company_id_str not in ("personal", "all") and not member_id_str:
            cid = int(company_id_str)
            members_result = await session.execute(
                select(CompanyMember, User)
                .join(User, User.id == CompanyMember.user_id)
                .where(CompanyMember.company_id == cid)
            )
            members = members_result.all()

            # Faqat is_responsible=True bo'lgan assignmentlar hisoblanadi
            emp_result = await session.execute(
                select(TaskAssignment.user_id, TaskAssignment.status, func.count(TaskAssignment.id))
                .join(Task, Task.id == TaskAssignment.task_id)
                .where(Task.company_id == cid)
                .where(Task.status.notin_([TaskStatus.CANCELLED]))
                .where(TaskAssignment.is_responsible == True)
                .group_by(TaskAssignment.user_id, TaskAssignment.status)
            )
            emp_stats_raw = emp_result.all()

            emp_map = {}
            for member, usr in members:
                emp_map[usr.id] = {
                    "id": usr.id, "name": usr.full_name, "role": member.role.value,
                    "done": 0, "overdue": 0, "in_progress": 0, "new": 0, "review": 0, "total": 0
                }

            for uid, status_val, count in emp_stats_raw:
                if uid not in emp_map:
                    continue
                st = status_val.value if hasattr(status_val, 'value') else str(status_val)
                if st == "done":          emp_map[uid]["done"] += count
                elif st == "overdue":     emp_map[uid]["overdue"] += count
                elif st == "in_progress": emp_map[uid]["in_progress"] += count
                elif st == "review":      emp_map[uid]["review"] += count
                elif st == "new":         emp_map[uid]["new"] += count
                emp_map[uid]["total"] += count
            employee_stats = list(emp_map.values())

    total = sum(status_counts.values())
    done = status_counts.get("done", 0)
    completion_rate = round((done / total * 100) if total > 0 else 0)

    overdue_active = status_counts.get("overdue", 0)
    overdue_total  = overdue_active + (late_done_count or 0)
    return web.json_response({
        "total": total,
        "new": status_counts.get("new", 0),
        "in_progress": status_counts.get("in_progress", 0),
        "review": status_counts.get("review", 0),
        "done": done,
        # KECHIKKAN — faqat foydalanuvchining MAS'UL vazifalari
        "overdue": my_overdue_total,
        # Workspace bo'yicha (mos kelganda kerak bo'lishi mumkin)
        "overdue_workspace": overdue_total,
        "overdue_active": overdue_active,
        "late_done": late_done_count,
        "my_overdue_active": my_overdue_active,
        "my_late_done": my_late_done,
        "cancelled": status_counts.get("cancelled", 0),
        "completion_rate": completion_rate,
        "employee_stats": employee_stats,
        "is_admin": is_admin,
        "is_company": is_company,
        "member_name": member_name,
    })


async def api_ai_status(request):
    """Mini app — foydalanuvchiga AI yoqilganmi tekshirish (tugmani ko'rsatish/yashirish)"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    return web.json_response({"ok": True, "ai_enabled": bool(getattr(user, "ai_enabled", False))})


async def api_ai_chat(request):
    """Mini app AI chat — vazifalar konteksti bilan to'liq funksional AI yordamchi"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    text = (body.get("message") or "").strip()
    if not text or len(text) > 2000:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Xabar 1-2000 belgi bo'lsin"}))

    company_id_str = (body.get("company_id") or "personal")
    history = body.get("history") or []

    # --- Foydalanuvchi vazifalarini yuklab kontekst tayyorlaymiz ---
    # MUHIM: AI faqat FOYDALANUVCHINING o'z vazifalarini ko'rishi kerak
    # (u yaratgan yoki unga biriktirilgan) — boshqalarning vazifalari emas!
    from sqlalchemy import or_
    async with get_session() as session:
        stmt = select(Task).outerjoin(TaskAssignment, TaskAssignment.task_id == Task.id)
        # Doimo foydalanuvchi bo'yicha filtr
        stmt = stmt.where(
            or_(Task.creator_id == user.id, TaskAssignment.user_id == user.id)
        )
        # Workspace doirasi (qo'shimcha)
        if company_id_str == "personal":
            stmt = stmt.where(Task.company_id.is_(None))
        elif company_id_str and company_id_str != "all":
            try:
                c_id_ctx = int(company_id_str)
                stmt = stmt.where(Task.company_id == c_id_ctx)
            except (ValueError, TypeError):
                pass  # noma'lum → barcha vazifalar (lekin baribir user bo'yicha filtrlangan)

        tasks_res = await session.execute(
            stmt.order_by(Task.created_at.desc()).distinct()
        )
        all_tasks = list(tasks_res.scalars().unique().all())

    tasks_ctx = []
    for t in all_tasks:
        tasks_ctx.append({
            "id": t.id,
            "title": t.title,
            "status": t.status.value if hasattr(t.status, "value") else (t.status or "new"),
            "priority": t.priority.value if hasattr(t.priority, "value") else (t.priority or "medium"),
            "deadline": t.deadline.isoformat() if t.deadline else None,
        })

    sc = {}
    for t in tasks_ctx:
        sc[t["status"]] = sc.get(t["status"], 0) + 1
    stats_ctx = {
        "total": len(tasks_ctx),
        "done": sc.get("done", 0),
        "in_progress": sc.get("in_progress", 0),
        "new": sc.get("new", 0),
        "overdue": sc.get("overdue", 0),
        "review": sc.get("review", 0),
    }

    # ===== AI MASLAHATCHI rejimi (advisory-only) =====
    # AI faqat admin yoqgan foydalanuvchilar uchun ishlaydi
    if not getattr(user, "ai_enabled", False):
        return web.json_response({
            "action": "reply",
            "ai_disabled": True,
            "text": "🔒 AI maslahatchi siz uchun hali yoqilmagan.\nIltimos, administrator bilan bog'laning — u sizga AI yordamchini yoqib beradi.",
        })

    consult = await AIService.consult_message(text, user.full_name, tasks_ctx, stats_ctx, history)
    c_action = consult.get("action", "reply")
    logger.info(f"[AI CONSULT] user={user.id} text={text!r} → {c_action}")

    # --- Eslatma qo'yish ---
    if c_action == "set_reminder":
        remind_raw = (consult.get("remind_at") or "").strip()
        rem_text = (consult.get("text") or "").strip() or "Eslatma"
        task_ref = consult.get("task_ref")
        remind_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                remind_dt = datetime.strptime(remind_raw, fmt)
                break
            except (ValueError, TypeError):
                continue
        if not remind_dt:
            return web.json_response({
                "action": "reply",
                "text": "⏰ Eslatma vaqtini aniq tushunmadim. Iltimos sana va soatni yozing — masalan: <b>ertaga 15:00</b>.",
            })
        # Mahalliy vaqtni (Asia/Tashkent) UTC ga aylantiramiz
        local_dt = remind_dt.replace(tzinfo=_TZ)
        remind_utc = local_dt.astimezone(_UTC)

        # task_ref bo'yicha vazifani topishga harakat
        matched_task_id = None
        matched_task_title = None
        if task_ref:
            ref_s = str(task_ref).strip().lower()
            for t in tasks_ctx:
                if ref_s and (ref_s == str(t["id"]) or ref_s in (t["title"] or "").lower()):
                    matched_task_id = t["id"]
                    matched_task_title = t["title"]
                    break

        now_utc = datetime.now(_UTC)

        # "Hozir" / yaqin vaqt (90 soniya ichida) — DARROV botdan eslatma yuboramiz
        if remind_utc <= now_utc + timedelta(seconds=90):
            import random as _rnd
            motiv = _rnd.choice([
                "💪 Sen bu ishni eplaysan!", "🚀 Bir qadam tashla — qolgani o'zi keladi!",
                "🔥 Diqqatni jamla va zarba ber!", "⭐ O'zingga ishon, sen ulgurasan!",
            ])
            task_line = f"\n📋 Vazifa: <b>{matched_task_title}</b>" if matched_task_title else ""
            bot = request.app.get("bot")
            sent = False
            if bot and getattr(user, "telegram_id", None):
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"🔔 <b>Eslatma!</b>\n\n«{rem_text}»{task_line}\n\n{motiv}",
                        parse_mode="HTML",
                    )
                    sent = True
                except Exception as e:
                    logger.warning(f"Darrov eslatma yuborilmadi: {e}")
            return web.json_response({
                "action": "reply",
                "reminder_set": True,
                "text": (
                    "✅ Mana, hoziroq botga eslatma yubordim! 🔔 Telegram'ni tekshiring 💪"
                    if sent else
                    f"🔔 <b>Eslatma!</b>\n«{rem_text}»\n\n{motiv}"
                ),
            })

        # Kelajak vaqt — jadvalga yozamiz (scheduler yuboradi)
        async with get_session() as session:
            rem = Reminder(
                user_id=user.id,
                task_id=matched_task_id,
                remind_at=remind_utc,
                text=rem_text,
            )
            session.add(rem)
            await session.commit()

        when_local = remind_dt.strftime("%d.%m.%Y %H:%M")
        return web.json_response({
            "action": "reply",
            "reminder_set": True,
            "text": f"✅ Yaxshi! <b>{when_local}</b> da botdan eslatib qo'yaman:\n«{rem_text}»\n\nO'shanda sizni ruhlantirib eslataman 💪",
        })

    # --- Oddiy maslahat/javob ---
    return web.json_response({
        "action": "reply",
        "text": (consult.get("text") or "Tushunmadim, qaytadan yozing.").strip(),
    })

    # ===== (eski task-yaratuvchi AI — endi ishlatilmaydi) =====
    result = await AIService.process_message_with_context(text, user.full_name, tasks_ctx, stats_ctx, history)
    action = result.get("action", "reply")
    reply = {"action": action}

    logger.info(f"[AI WEB] user={user.id} text={text!r} → action={action} result={result}")

    # ===== ASK MORE (AI tafsilotlarni so'raydi) =====
    if action == "ask_more":
        ask_text = (result.get("text") or "Yana qo'shimcha ma'lumot kerak.").strip()
        draft = result.get("draft") or {}
        reply.update({
            "action": "ask_more",
            "text": ask_text,
            "draft": {
                "title": draft.get("title"),
                "description": draft.get("description"),
                "priority": draft.get("priority"),
                "deadline": draft.get("deadline"),
            },
        })
        return web.json_response(reply)

    # ===== PROPOSE TASK (foydalanuvchi tasdiqlashi shart) =====
    if action == "propose_task" or action == "create_task":
        title = (result.get("title") or "").strip()
        desc = (result.get("description") or "").strip()
        prio = result.get("priority") or "medium"
        dl_str = result.get("deadline")

        # Majburiy maydonlarni tekshiramiz — yo'q bo'lsa qaytarib so'raymiz
        missing = []
        if not title: missing.append("nom")
        if not desc: missing.append("tavsif")
        if not dl_str: missing.append("deadline")

        if missing:
            qmap = {
                "nom": "vazifa NOMI nima bo'lsin?",
                "tavsif": "qisqacha TAVSIFI ham kerak — nima qilish kerak?",
                "deadline": "DEADLINE qachon? Sana va vaqtni yozing (masalan: ertaga 15:00 yoki 26.04.2026 18:00)",
            }
            ask = "Vazifa yaratish uchun yana shu ma'lumot kerak: " + ", ".join(qmap[m] for m in missing)
            reply.update({
                "action": "ask_more",
                "text": ask,
                "draft": {
                    "title": title or None,
                    "description": desc or None,
                    "priority": prio,
                    "deadline": dl_str,
                },
            })
            return web.json_response(reply)

        # Deadline ni parse qilamiz — VAQT MAJBURIY (HH:MM)
        deadline = None
        try:
            deadline = datetime.strptime(dl_str, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            deadline = None

        if not deadline:
            reply.update({
                "action": "ask_more",
                "text": "⏰ Deadline VAQTI ham kerak! Iltimos sana va soatni birga yozing — masalan: <code>ertaga 15:00</code> yoki <code>26.04.2026 18:00</code>",
                "draft": {"title": title, "description": desc, "priority": prio, "deadline": None},
            })
            return web.json_response(reply)

        if deadline.hour == 0 and deadline.minute == 0:
            reply.update({
                "action": "ask_more",
                "text": (
                    f"⏰ Deadline vaqti aniqlanmadi (faqat sana: <b>{deadline.strftime('%d.%m.%Y')}</b>).\n"
                    "Iltimos, soatni ham yozing — masalan: <code>15:00</code> yoki <code>18:30</code>"
                ),
                "draft": {"title": title, "description": desc, "priority": prio, "deadline": deadline.strftime("%Y-%m-%d")},
            })
            return web.json_response(reply)

        dl_fmt = deadline.strftime("%d.%m.%Y %H:%M")
        pnames = {"low": "🟢 Past", "medium": "🟡 O'rta", "high": "🟠 Yuqori", "urgent": "🔴 Muhim"}
        pn = pnames.get(prio, "🟡 O'rta")

        # Workspace nomi
        ws_label = "👤 Shaxsiy"
        if company_id_str and company_id_str != "personal":
            try:
                c_id_tmp = int(company_id_str)
                async with get_session() as _s2:
                    co = await _s2.execute(select(Company).where(Company.id == c_id_tmp))
                    co_obj = co.scalar_one_or_none()
                    if co_obj:
                        ws_label = f"🏢 {co_obj.name}"
            except Exception:
                pass

        # Taklif qilingan vazifa — TASDIQ so'rash uchun
        proposal_text = (
            "📋 <b>Vazifa tafsilotlari (tasdiqlashingiz uchun):</b>\n\n"
            f"📌 <b>Nomi:</b> {_he(title)}\n"
            f"📝 <b>Tavsif:</b> {_he(desc)}\n"
            f"⚡ <b>Muhimlik:</b> {pn}\n"
            f"⏰ <b>Deadline:</b> {dl_fmt}\n"
            f"📁 <b>Workspace:</b> {_he(ws_label)}\n\n"
            "Hammasi to'g'rimi? Quyidagi tugmalardan birini tanlang."
        )

        reply.update({
            "action": "propose_task",
            "text": proposal_text,
            "proposal": {
                "title": title,
                "description": desc,
                "priority": prio,
                "deadline": dl_str,  # ISO format yuboramiz, confirm endpoint bunga ishlaydi
                "deadline_display": dl_fmt,
                "workspace_label": ws_label,
                "company_id": company_id_str,
            },
        })
        return web.json_response(reply)

    # ===== LIST TASKS =====
    elif action == "list_tasks":
        filter_val = result.get("filter", "active")
        filtered = tasks_ctx
        if filter_val == "active":
            filtered = [t for t in tasks_ctx if t["status"] not in ("done", "cancelled")]
        elif filter_val == "done":
            filtered = [t for t in tasks_ctx if t["status"] == "done"]
        elif filter_val == "urgent":
            filtered = [t for t in tasks_ctx if t["priority"] == "urgent"]
        elif filter_val == "overdue":
            filtered = [t for t in tasks_ctx if t["status"] == "overdue"]

        if not filtered:
            label_map = {"active": "faol", "done": "bajarilgan", "urgent": "juda muhim", "overdue": "kechikkan"}
            reply.update({"text": f"Hozircha {label_map.get(filter_val, '')} vazifalar yo'q. 🎉"})
            return web.json_response(reply)

        S_ICON = {"new": "🆕", "in_progress": "⚙️", "done": "✅", "overdue": "⏰", "review": "🔍", "cancelled": "🚫"}
        P_ICON = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        lines = [f"📋 <b>Vazifalar ({len(filtered)} ta):</b>"]
        for i, t in enumerate(filtered[:15], 1):
            si = S_ICON.get(t["status"], "•")
            pi = P_ICON.get(t["priority"], "")
            dl = ""
            if t.get("deadline"):
                try:
                    d = datetime.fromisoformat(t["deadline"])
                    dl = f" · {d.strftime('%d.%m')}"
                except Exception:
                    pass
            lines.append(f"{i}. {si}{pi} {_he(t['title'])}{dl}")
        if len(filtered) > 15:
            lines.append(f"<i>...va yana {len(filtered) - 15} ta</i>")

        reply.update({"text": "\n".join(lines), "tasks": filtered[:15]})
        return web.json_response(reply)

    # ===== SHOW STATS =====
    elif action == "show_stats":
        total = stats_ctx["total"]
        done = stats_ctx["done"]
        rate = round(done / total * 100) if total else 0
        msg = (
            f"📊 <b>Sizning statistikangiz:</b>\n\n"
            f"📌 Jami: <b>{total}</b> ta vazifa\n"
            f"✅ Bajarildi: <b>{done}</b> ta\n"
            f"⚙️ Jarayonda: <b>{stats_ctx['in_progress']}</b> ta\n"
            f"🆕 Yangi: <b>{stats_ctx['new']}</b> ta\n"
            f"⏰ Kechikdi: <b>{stats_ctx['overdue']}</b> ta\n"
            f"📈 Bajarilish darajasi: <b>{rate}%</b>"
        )
        reply.update({"text": msg})
        return web.json_response(reply)

    # ===== UPDATE TASK =====
    elif action == "update_task":
        task_ref = str(result.get("task_ref", "")).strip()
        new_status_str = result.get("new_status", "done")

        found_task = None
        try:
            ref_id = int(task_ref)
            found_task = next((t for t in all_tasks if t.id == ref_id), None)
        except (ValueError, TypeError):
            trl = task_ref.lower()
            for t in all_tasks:
                if trl in t.title.lower():
                    found_task = t
                    break

        if not found_task:
            reply.update({"action": "reply", "text": f"«{_he(task_ref)}» nomli vazifa topilmadi. Ro'yxatni ko'ring yoki to'liq nomini yozing."})
            return web.json_response(reply)

        try:
            new_status = TaskStatus(new_status_str)
        except ValueError:
            new_status = TaskStatus.DONE

        async with get_session() as session:
            a_res = await session.execute(
                select(TaskAssignment).where(
                    and_(TaskAssignment.task_id == found_task.id, TaskAssignment.user_id == user.id)
                )
            )
            assignment = a_res.scalar_one_or_none()
            if assignment:
                assignment.status = new_status.value
                if new_status == TaskStatus.DONE:
                    assignment.completed_at = datetime.now(_UTC)
                # Umumiy task statusini tekshirish (masul ijrochilar asosida)
                all_asgn_res = await session.execute(
                    select(TaskAssignment).where(TaskAssignment.task_id == found_task.id)
                )
                all_asgn = all_asgn_res.scalars().all()
                task_db_res = await session.execute(select(Task).where(Task.id == found_task.id))
                task_db = task_db_res.scalar_one()
                computed = _compute_task_status(all_asgn, task_db.status)
                if computed != task_db.status:
                    task_db.status = computed
                    if computed == TaskStatus.DONE:
                        task_db.completed_at = datetime.now(_UTC)
            else:
                task_db_res = await session.execute(select(Task).where(Task.id == found_task.id))
                task_db = task_db_res.scalar_one()
                task_db.status = new_status
                if new_status == TaskStatus.DONE:
                    task_db.completed_at = datetime.now(_UTC)

            session.add(TaskHistory(
                task_id=found_task.id, user_id=user.id, action="my_status_changed",
                new_value={"status": new_status.value, "source": "ai_chat"},
            ))
            await session.commit()

        STATUS_NAMES = {
            "in_progress": "Jarayonda ⚙️", "done": "Bajarildi ✅",
            "review": "Ko'rilmoqda 🔍", "cancelled": "Bekor qilindi 🚫", "new": "Yangi 🆕",
        }
        st_name = STATUS_NAMES.get(new_status.value, new_status.value)
        reply.update({
            "text": f"✅ <b>«{_he(found_task.title)}»</b>\nYangi status: {st_name}",
            "task_id": found_task.id,
            "refreshTasks": True,
        })
        return web.json_response(reply)

    # ===== SEARCH TASKS =====
    elif action == "search_tasks":
        query = (result.get("query") or "").lower().strip()
        if not query:
            reply.update({"action": "reply", "text": "Nima qidirmoqchisiz? Vazifa nomini yozing."})
            return web.json_response(reply)

        found = [t for t in tasks_ctx if query in t["title"].lower()]
        if not found:
            reply.update({"text": f"«{_he(query)}» bo'yicha hech narsa topilmadi."})
            return web.json_response(reply)

        S_ICON = {"new": "🆕", "in_progress": "⚙️", "done": "✅", "overdue": "⏰", "review": "🔍", "cancelled": "🚫"}
        lines = [f"🔍 <b>Natijalar ({len(found)} ta):</b>"]
        for t in found[:10]:
            si = S_ICON.get(t["status"], "•")
            lines.append(f"• {si} {_he(t['title'])} <i>(ID:{t['id']})</i>")

        reply.update({"text": "\n".join(lines), "tasks": found[:10]})
        return web.json_response(reply)

    # ===== DELETE TASK =====
    elif action == "delete_task":
        task_ref = str(result.get("task_ref", "")).strip()
        found_task = None
        try:
            ref_id = int(task_ref)
            found_task = next((t for t in all_tasks if t.id == ref_id), None)
        except (ValueError, TypeError):
            trl = task_ref.lower()
            for t in all_tasks:
                if trl in t.title.lower():
                    found_task = t
                    break

        if not found_task:
            reply.update({"action": "reply", "text": f"«{_he(task_ref)}» nomli vazifa topilmadi."})
            return web.json_response(reply)

        # Faqat creator o'chira oladi — status cancelled qo'yamiz
        if found_task.creator_id != user.id:
            reply.update({"action": "reply", "text": "Siz faqat o'zingiz yaratgan vazifalarni o'chira olasiz."})
            return web.json_response(reply)

        async with get_session() as session:
            task_db_res = await session.execute(select(Task).where(Task.id == found_task.id))
            task_db = task_db_res.scalar_one_or_none()
            if task_db:
                task_db.status = TaskStatus.CANCELLED
                session.add(TaskHistory(
                    task_id=found_task.id, user_id=user.id, action="status_changed",
                    new_value={"status": "cancelled", "source": "ai_chat"},
                ))
                await session.commit()

        reply.update({
            "text": f"🗑 <b>«{_he(found_task.title)}»</b> bekor qilindi.",
            "refreshTasks": True,
        })
        return web.json_response(reply)

    # ===== REPLY (default) =====
    reply.update({"text": result.get("text", "Tushunmadim, qaytadan ayting.")})
    return web.json_response(reply)


def _he(text: str) -> str:
    """HTML escape helper"""
    import html
    return html.escape(str(text))


async def api_get_workspaces(request):
    """Foydalanuvchining hamma workspacelari (kompaniyalari)"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    async with get_session() as session:
        result = await session.execute(
            select(Company)
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user.id)
            .order_by(Company.name)
        )
        companies = result.unique().scalars().all()

    workspaces = [{"id": "personal", "name": "Shaxsiy", "is_owner": False, "is_admin": False}]
    async with get_session() as session2:
        for c in companies:
            # Count members
            cnt_res = await session2.execute(
                select(func.count()).select_from(CompanyMember).where(CompanyMember.company_id == c.id)
            )
            member_count = cnt_res.scalar() or 0
            # Check current user role
            role_res = await session2.execute(
                select(CompanyMember.role).where(
                    CompanyMember.company_id == c.id,
                    CompanyMember.user_id == user.id,
                )
            )
            user_role = role_res.scalar_one_or_none()
            is_owner = c.owner_id == user.id
            is_admin = is_owner or (user_role in (CompanyRole.OWNER, CompanyRole.ADMIN))
            # Telegram group link if available
            tg_group_id = getattr(c, 'telegram_group_id', None)
            workspaces.append({
                "id": c.id,
                "name": c.name,
                "is_owner": is_owner,
                "is_admin": is_admin,
                "member_count": member_count,
                "telegram_group_id": tg_group_id,
            })

    return web.json_response({"workspaces": workspaces})


async def api_leave_company(request):
    """Mini App'dan kompaniya/guruhdan chiqish"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        company_id = int(request.match_info["company_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid company_id"}, status=400)

    from database.models import GroupMember as GM, Group as GModel
    async with get_session() as session:
        # Check membership
        member_res = await session.execute(
            select(CompanyMember).where(
                and_(
                    CompanyMember.company_id == company_id,
                    CompanyMember.user_id == user.id,
                )
            )
        )
        member = member_res.scalar_one_or_none()

        if not member:
            return web.json_response({"error": "Siz bu kompaniya a'zosi emassiz"}, status=404)

        # Can't leave if you're the owner
        company_res = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_res.scalar_one_or_none()
        if company and company.owner_id == user.id:
            return web.json_response(
                {"error": "Kompaniya egasi kompaniyadan chiqa olmaydi"},
                status=403,
            )

        # Company name for notification
        company_name = company.name if company else "Jamoa"

        # Collect remaining members for notification
        all_members_res = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id != user.id,
            )
        )
        remaining_members = all_members_res.scalars().all()
        remaining_ids = [m.user_id for m in remaining_members]

        # Remove from company
        await session.delete(member)

        # Remove from associated groups
        group_res = await session.execute(
            select(GModel).where(GModel.company_id == company_id)
        )
        groups = group_res.scalars().all()
        for g in groups:
            gm_res = await session.execute(
                select(GM).where(GM.group_id == g.id, GM.user_id == user.id)
            )
            gm = gm_res.scalar_one_or_none()
            if gm:
                await session.delete(gm)

        await session.commit()

    # Notify remaining members via bot
    bot = request.app.get("bot")
    if bot and remaining_ids:
        notify_text = (
            f"🚪 <b>{user.full_name}</b> "
            f"<b>{company_name}</b> jamoasidan chiqdi."
        )
        for uid in remaining_ids:
            try:
                await bot.send_message(uid, notify_text, parse_mode="HTML")
            except Exception:
                pass

    return web.json_response({"ok": True, "message": "Kompaniyadan chiqdingiz"})


async def api_delete_company(request):
    """DELETE /api/companies/{company_id} — faqat owner o'chira oladi"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        company_id = int(request.match_info["company_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid company_id"}, status=400)

    async with get_session() as session:
        company_res = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_res.scalar_one_or_none()
        if not company:
            return web.json_response({"error": "Jamoa topilmadi"}, status=404)
        if company.owner_id != user.id:
            return web.json_response({"error": "Faqat jamoa egasi o'chira oladi"}, status=403)
        company_name = company.name
        ok = await CompanyService.delete_company(session, company_id, user.id)
        if not ok:
            return web.json_response({"error": "O'chirib bo'lmadi"}, status=500)
        await session.commit()

    return web.json_response({"ok": True, "deleted": company_name})


async def api_get_invite_link(request):
    """Bot invite havolasini qaytaradi"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    bot_username = settings.BOT_USERNAME.lstrip("@")
    # start payload: invite_{user_id} — bot shu token bilan kimni taklif qilganini biladi
    start_payload = f"invite_{user.id}"
    link = f"https://t.me/{bot_username}?start={start_payload}"
    return web.json_response({"link": link, "bot_username": bot_username})


async def api_get_company_info(request):
    """Kompaniya ma'lumotlari (foydalanuvchi roli bilan)"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "Unauthorized"}))

    try:
        company_id = int(request.match_info["company_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid company_id"}, status=400)

    async with get_session() as session:
        company_res = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_res.scalar_one_or_none()
        if not company:
            return web.json_response({"error": "Topilmadi"}, status=404)

        member_res = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user.id,
            )
        )
        my_member = member_res.scalar_one_or_none()
        if not my_member:
            return web.json_response({"error": "Ruxsat yo'q"}, status=403)

        is_owner = company.owner_id == user.id

        # Get all members with user info
        from database.models import User as UserModel
        all_members_res = await session.execute(
            select(CompanyMember, UserModel)
            .join(UserModel, CompanyMember.user_id == UserModel.id)
            .where(CompanyMember.company_id == company_id)
        )
        members = []
        for cm, u in all_members_res.all():
            role_val = cm.role.value if hasattr(cm.role, "value") else (cm.role or "member")
            members.append({
                "id": u.id,
                "name": u.full_name,
                "username": u.username or "",
                "role": role_val,
                "is_self": u.id == user.id,
                "is_owner": u.id == company.owner_id,
            })

    return web.json_response({
        "id": company.id,
        "name": company.name,
        "is_owner": is_owner,
        "my_role": my_member.role.value if hasattr(my_member.role, "value") else str(my_member.role),
        "members": members,
    })


async def api_remove_company_member(request):
    """Kompaniyadan a'zoni chiqarish (faqat owner)"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "Unauthorized"}))

    try:
        company_id = int(request.match_info["company_id"])
        target_user_id = int(request.match_info["user_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid id"}, status=400)

    from database.models import Group as GModel, GroupMember as GM

    async with get_session() as session:
        company_res = await session.execute(select(Company).where(Company.id == company_id))
        company = company_res.scalar_one_or_none()
        if not company:
            return web.json_response({"error": "Topilmadi"}, status=404)
        if company.owner_id != user.id:
            return web.json_response({"error": "Faqat owner a'zoni chiqara oladi"}, status=403)
        if target_user_id == user.id:
            return web.json_response({"error": "O'zingizni chiqara olmaysiz"}, status=400)

        member_res = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == target_user_id,
            )
        )
        member = member_res.scalar_one_or_none()
        if not member:
            return web.json_response({"error": "A'zo topilmadi"}, status=404)

        # Get target user info
        from database.models import User as UserModel
        target_res = await session.execute(select(UserModel).where(UserModel.id == target_user_id))
        target_user = target_res.scalar_one_or_none()
        target_name = target_user.full_name if target_user else "Foydalanuvchi"

        await session.delete(member)

        # Remove from groups
        group_res = await session.execute(select(GModel).where(GModel.company_id == company_id))
        for g in group_res.scalars().all():
            gm_res = await session.execute(
                select(GM).where(GM.group_id == g.id, GM.user_id == target_user_id)
            )
            gm = gm_res.scalar_one_or_none()
            if gm:
                await session.delete(gm)

        await session.commit()

    # Notify removed user and owner
    bot = request.app.get("bot")
    if bot:
        try:
            await bot.send_message(
                target_user_id,
                f"🚪 Siz <b>{company.name}</b> jamoasidan chiqarildingiz.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    return web.json_response({"ok": True, "removed_name": target_name})


async def api_update_member(request):
    """PUT /api/companies/{company_id}/members/{user_id} — update member role/position"""
    current_user = await get_user_from_request(request)
    if not current_user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "Unauthorized"}), content_type="application/json")

    try:
        company_id = int(request.match_info['company_id'])
        target_user_id = int(request.match_info['user_id'])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid ids"}, status=400)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "JSON xato"}, status=400)

    async with get_session() as session:
        # Check current user is admin or owner
        admin_check = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == current_user.id,
                CompanyMember.role.in_([CompanyRole.OWNER, CompanyRole.ADMIN])
            )
        )
        if not admin_check.scalar_one_or_none():
            return web.json_response({"error": "Ruxsat yo'q"}, status=403)

        # Get target member
        member_res = await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == target_user_id
            )
        )
        member = member_res.scalar_one_or_none()
        if not member:
            return web.json_response({"error": "A'zo topilmadi"}, status=404)

        # Update position/role
        if 'position' in body:
            member.position = body['position']
        if 'role' in body and body['role'] in [r.value for r in CompanyRole]:
            member.role = CompanyRole(body['role'])

        await session.commit()
        return web.json_response({"ok": True})


async def api_reassign_tasks(request):
    """Bir foydalanuvchi vazifalarini boshqasiga topshirish (owner only)"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPUnauthorized(text=json.dumps({"error": "Unauthorized"}))

    try:
        company_id = int(request.match_info["company_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid company_id"}, status=400)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "JSON xato"}, status=400)

    from_user_id = body.get("from_user_id")
    to_user_id = body.get("to_user_id")

    if not from_user_id or not to_user_id:
        return web.json_response({"error": "from_user_id va to_user_id kerak"}, status=400)

    async with get_session() as session:
        company_res = await session.execute(select(Company).where(Company.id == company_id))
        company = company_res.scalar_one_or_none()
        if not company or company.owner_id != user.id:
            return web.json_response({"error": "Ruxsat yo'q"}, status=403)

        # Reassign all active assignments
        from database.models import TaskAssignment
        asgn_res = await session.execute(
            select(TaskAssignment).where(
                TaskAssignment.user_id == from_user_id,
                TaskAssignment.status != "done",
            )
        )
        reassigned = 0
        for asgn in asgn_res.scalars().all():
            # Check if target already assigned to this task
            existing = await session.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == asgn.task_id,
                    TaskAssignment.user_id == to_user_id,
                )
            )
            if not existing.scalar_one_or_none():
                asgn.user_id = to_user_id
                reassigned += 1

        await session.commit()

    return web.json_response({"ok": True, "reassigned": reassigned})


# ===== Helpers =====

def _rel_loaded_bool(obj, rel_name: str) -> bool:
    """Relationship eager-load qilingan bo'lsagina uni o'qiydi (async lazy-load crashni oldini oladi).
    Yuklanmagan bo'lsa — False qaytaradi (load'ni trigger qilmaydi)."""
    try:
        from sqlalchemy import inspect as _sa_inspect
        state = _sa_inspect(obj)
        if rel_name in state.unloaded:
            return False
        val = getattr(obj, rel_name, None)
        return bool(val)
    except Exception:
        return False


def _activate_step(step, now=None) -> None:
    """Workflow qadamini AKTIV qiladi.

    NISBIY MUDDAT: `duration_days` bo'lsa, deadline aynan shu paytdan qayta hisoblanadi
    (aktivlashgan vaqt + N kun) — oldingi qadam kechikkani keyingi odamga o'tmaydi.
    """
    if now is None:
        now = datetime.now(_UTC)
    step.status = "active"
    step.started_at = now
    step.completed_at = None
    d = getattr(step, "duration_days", None)
    if d:
        try:
            step.deadline = now + timedelta(days=int(d))
        except (ValueError, TypeError):
            pass
    for _f in ("step_warned_morning", "step_warned_3h", "step_warned_2h",
               "step_warned_1h", "step_warned_exact"):
        if hasattr(step, _f):
            setattr(step, _f, False)


def _project_step_dates(steps, now=None) -> dict:
    """Workflow qadamlari uchun TAXMINIY (proyeksiya) sanalarni hisoblaydi.

    Navbati kelmagan (pending) qadamda aniq sana yo'q, faqat `duration_days` bo'lsa —
    oldingi qadamning sanasidan (yoki haqiqiy tugash vaqtidan) zanjir bo'yicha
    taxminiy sana chiqariladi:

        #1 → 05.08 (aniq sana)
        #2 → 2 kun  ⇒ taxminan 07.08
        #3 → 3 kun  ⇒ taxminan 10.08

    Qaytaradi: {step_id: datetime} — faqat taxminiy hisoblanganlar uchun.
    """
    if now is None:
        now = datetime.now(_UTC)
    projected = {}
    cursor = None
    for s in sorted(steps, key=lambda x: (x.order_index or 0)):
        st = (s.status or "pending")
        if st in ("done", "skipped"):
            # Haqiqiy tugash vaqti — keyingi qadamlar uchun asos
            cursor = s.completed_at or s.deadline or cursor
            continue
        if s.deadline:
            # Aniq sanasi bor — proyeksiya kerak emas
            cursor = s.deadline
            continue
        d = getattr(s, "duration_days", None)
        if d:
            base = cursor or now
            try:
                est = base + timedelta(days=int(d))
            except (ValueError, TypeError):
                continue
            projected[s.id] = est
            cursor = est
    return projected


def _task_to_dict(task: Task) -> dict:
    """Task modelini JSON formatga o'girish"""
    responsible = next((a for a in (task.assignments or []) if a.is_responsible and a.user), None)
    d = {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority": task.priority.value,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "creator_name": task.creator.full_name if task.creator else None,
        "creator_id": task.creator_id,
        "parent_id": getattr(task, "parent_id", None),
        "subtasks_count": len(task.subtasks) if hasattr(task, 'subtasks') and task.subtasks else 0,
        "responsible_id": responsible.user_id if responsible else None,
        "responsible_name": responsible.user.full_name if responsible else None,
        "has_workflow": _rel_loaded_bool(task, "steps"),
        "assignees": [
            {
                "id": a.user.id if a.user else a.user_id,
                "name": a.user.full_name if a.user else "Noma'lum",
                "status": (a.status.value if hasattr(a.status, "value") else (a.status or "new")),
                "is_responsible": bool(a.is_responsible),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in (task.assignments or [])
        ],
    }
    try:
        d["attachments"] = [
            {
                "id": att.id, "file_type": att.file_type,
                "file_name": att.file_name, "file_url": att.file_url,
                "file_size": att.file_size, "mime_type": att.mime_type,
                "created_at": att.created_at.isoformat() if att.created_at else None,
                "uploader_id": att.user_id,
                "uploader_name": att.user.full_name if att.user else None,
            }
            for att in (task.attachments or [])
        ]
    except Exception:
        d["attachments"] = []
    try:
        d["subtasks"] = [
            {
                "id": s.id, "title": s.title, "status": s.status.value,
                "priority": s.priority.value,
                "deadline": s.deadline.isoformat() if s.deadline else None,
            }
            for s in (task.subtasks or [])
        ]
    except Exception:
        d["subtasks"] = []
    return d


ATTACH_DIR = Path(__file__).parent.parent / "uploads"
ATTACH_DIR.mkdir(exist_ok=True)


async def api_update_priority(request):
    """Vazifa muhimlik darajasini yangilash"""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    try:
        priority = Priority(body.get("priority", "medium"))
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Muhimlik noto'g'ri"}))

    async with get_session() as session:
        res = await session.execute(select(Task).where(Task.id == task_id))
        task = res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(text=json.dumps({"error": "Vazifa topilmadi"}))
        old = task.priority.value
        task.priority = priority
        session.add(TaskHistory(
            task_id=task.id, user_id=user.id, action="priority_changed",
            old_value={"priority": old}, new_value={"priority": priority.value},
        ))
    return web.json_response({"ok": True, "priority": priority.value})


async def api_edit_task(request):
    """Vazifani tahrirlash — FAQAT yaratuvchi (title, desc, priority, deadline)."""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    async with get_session() as session:
        res = await session.execute(
            select(Task).where(Task.id == task_id).options(
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
            )
        )
        task = res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(text=json.dumps({"error": "Vazifa topilmadi"}))
        if task.creator_id != user.id:
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Faqat vazifa yaratuvchisi tahrirlay oladi"}),
                content_type="application/json",
            )

        changes = []
        if "title" in body:
            nt = (body["title"] or "").strip()
            if len(nt) >= 2 and nt != task.title:
                changes.append("sarlavha")
                task.title = nt
        if "description" in body:
            nd = body["description"] or None
            if nd != task.description:
                changes.append("tavsif")
                task.description = nd
        if "priority" in body and body["priority"]:
            try:
                np = Priority(body["priority"])
                if np != task.priority:
                    changes.append("muhimlik")
                    task.priority = np
            except ValueError:
                pass
        deadline_changed = False
        if "deadline" in body:
            raw = body["deadline"]
            if raw in (None, "", "null"):
                if task.deadline is not None:
                    changes.append("deadline olib tashlandi")
                    task.deadline = None
                    deadline_changed = True
            else:
                try:
                    nd = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if nd.tzinfo is None:
                        nd = nd.replace(tzinfo=_UTC)
                    if nd != task.deadline:
                        old_dl = task.deadline
                        task.deadline = nd
                        deadline_changed = True
                        # deadline cho'zilsa va status overdue bo'lsa — qayta ochamiz
                        if task.status == TaskStatus.OVERDUE and nd > datetime.now(_UTC):
                            task.status = TaskStatus.IN_PROGRESS
                        changes.append("deadline yangilandi")
                except Exception:
                    raise web.HTTPBadRequest(text=json.dumps({"error": "Deadline noto'g'ri"}))

        if not changes:
            return web.json_response({"ok": True, "message": "O'zgarish yo'q"})

        session.add(TaskHistory(
            task_id=task.id, user_id=user.id, action="title_changed",
            old_value={}, new_value={"title": task.title, "edited": ", ".join(changes)},
        ))
        recipient_ids = {a.user_id for a in (task.assignments or [])}
        recipient_ids.discard(user.id)
        title = task.title
        new_deadline = task.deadline
        await session.commit()

    # Deadline cho'zilsa — mas'ullarga xabar
    bot = request.app.get("bot")
    if bot and deadline_changed:
        for uid in recipient_ids:
            try:
                async with get_session() as ns:
                    u = await ns.get(User, uid)
                if u and u.telegram_id:
                    dl_txt = (
                        new_deadline.astimezone(_TZ).strftime("%d.%m.%Y %H:%M")
                        if new_deadline else "olib tashlandi"
                    )
                    await bot.send_message(
                        u.telegram_id,
                        f"📅 <b>Deadline yangilandi</b>\n\n"
                        f"📋 <b>{title}</b>\n"
                        f"👤 {user.full_name} muddatni o'zgartirdi.\n"
                        f"⏰ Yangi muddat: <b>{dl_txt}</b>",
                    )
            except Exception as e:
                logger.warning(f"deadline notify uid={uid}: {e}")

    return web.json_response({
        "ok": True, "message": f"✅ Yangilandi: {', '.join(changes)}", "changes": changes,
    })


async def api_task_start(request):
    """Task boshlash — new/in_progress → in_progress, history log"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid task_id"}, status=400)

    task_ref = None
    old_status = None
    recipient_ids = set()

    async with get_session() as session:
        task_res = await session.execute(
            select(Task).where(Task.id == task_id)
            .options(selectinload(Task.assignments))
        )
        task = task_res.scalar_one_or_none()
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        if not await _user_can_access_task(session, user, task):
            return web.json_response({"error": "forbidden"}, status=403)

        # Mening assignment statusini topish
        asg_res = await session.execute(
            select(TaskAssignment).where(
                (TaskAssignment.task_id == task_id) & (TaskAssignment.user_id == user.id)
            )
        )
        asg = asg_res.scalar_one_or_none()

        if not asg:
            return web.json_response({"error": "not assigned"}, status=403)
        # Faqat mas'ul (responsible) ijrochi statusni o'zgartira oladi.
        # Yaratuvchi avtomatik mas'ul hisoblanmaydi — agar status o'zgartirmoqchi
        # bo'lsa, o'zini ham mas'ul qilib qo'shishi kerak.
        if not asg.is_responsible:
            return web.json_response({"error": "observer_only"}, status=403)

        old_status = asg.status
        started = False
        if asg.status in ("new", "pending", None):
            asg.status = "in_progress"
            # Reyting hisoblash uchun — birinchi marta jarayonga tushganda
            if not asg.started_at:
                asg.started_at = datetime.now(_UTC)
            started = True
            hist = TaskHistory(
                task_id=task_id, user_id=user.id, action="status_changed",
                old_value={"status": old_status}, new_value={"status": "in_progress"}
            )
            session.add(hist)

        # Recipient IDlarni yig'amiz (commit oldidan)
        recipient_ids.add(task.creator_id)
        for a in task.assignments:
            recipient_ids.add(a.user_id)
        task_ref = task

        await session.commit()

    # Notifications
    if started:
        bot = request.app.get("bot")
        if bot:
            # Shaxsiy xabar — o'zidan boshqalarga
            notify_ids = recipient_ids - {user.id}
            if notify_ids:
                try:
                    async with get_session() as ns:
                        await NotificationService.notify_my_status_changed(
                            bot, ns, task_ref, "in_progress", user.full_name,
                            recipient_ids=notify_ids,
                        )
                except Exception as e:
                    logger.warning(f"task_start personal notification xatosi: {e}")

            # Guruh chatiga
            try:
                async with get_session() as gs:
                    grp_tg_id = await _get_task_group_tg_id(gs, task_ref)
                    if grp_tg_id:
                        await NotificationService.notify_group_status_changed(
                            bot, grp_tg_id, task_ref,
                            old_status or "new", "in_progress", user.full_name,
                        )
            except Exception as e:
                logger.warning(f"task_start guruh notification xatosi: {e}")

    return web.json_response({"ok": True, "status": "in_progress" if started else asg.status})


async def api_task_complete(request):
    """Task tugatish — in_progress → done + comment, history log"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        task_id = int(request.match_info["task_id"])
        body = await request.json()
    except:
        return web.json_response({"error": "invalid request"}, status=400)

    comment = (body.get("comment") or "").strip()[:2000] or None

    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        if not await _user_can_access_task(session, user, task):
            return web.json_response({"error": "forbidden"}, status=403)

        asg_res = await session.execute(
            select(TaskAssignment).where(
                (TaskAssignment.task_id == task_id) & (TaskAssignment.user_id == user.id)
            )
        )
        asg = asg_res.scalar_one_or_none()

        if not asg:
            return web.json_response({"error": "not assigned"}, status=403)
        # Faqat mas'ul (responsible) ijrochi statusni o'zgartira oladi.
        # Yaratuvchi avtomatik mas'ul hisoblanmaydi — agar status o'zgartirmoqchi
        # bo'lsa, o'zini ham mas'ul qilib qo'shishi kerak.
        if not asg.is_responsible:
            return web.json_response({"error": "observer_only"}, status=403)

        old_status = asg.status
        asg.status = "done"
        _now = datetime.now(_UTC)
        asg.completed_at = _now
        # Reyting hisoblash uchun — vazifani bajarish davomiyligi (sekundlarda)
        if asg.started_at:
            started = asg.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=_UTC)
            delta = (_now - started).total_seconds()
            if delta > 0:
                asg.duration_seconds = int(delta)

        # History
        hist = TaskHistory(
            task_id=task_id, user_id=user.id, action="status_changed",
            old_value={"status": old_status}, new_value={"status": "done"}
        )
        session.add(hist)

        # Comment
        if comment:
            session.add(TaskComment(task_id=task_id, user_id=user.id, content=comment))

        # Recipient IDlarni commit oldidan yig'amiz
        all_asg_res = await session.execute(
            select(TaskAssignment).where(TaskAssignment.task_id == task_id)
        )
        all_assignees = all_asg_res.scalars().all()
        recipient_ids = {task.creator_id}
        for a in all_assignees:
            recipient_ids.add(a.user_id)

        await session.commit()

        # Umumiy statusni masul ijrochilar asosida hisoblaymiz (bot bilan bir xil)
        computed = _compute_task_status(all_assignees, task.status)
        all_done = computed == TaskStatus.DONE
        if computed != task.status:
            task.status = computed
            if computed == TaskStatus.DONE:
                task.completed_at = datetime.now(_UTC)
            await session.commit()

    # Notifications
    bot = request.app.get("bot")
    if bot:
        notify_ids = recipient_ids - {user.id}
        if notify_ids:
            try:
                async with get_session() as ns:
                    await NotificationService.notify_my_status_changed(
                        bot, ns, task, "done", user.full_name,
                        recipient_ids=notify_ids,
                    )
            except Exception as e:
                logger.warning(f"task_complete personal notification xatosi: {e}")

        try:
            async with get_session() as gs:
                grp_tg_id = await _get_task_group_tg_id(gs, task)
                if grp_tg_id:
                    label = "done" if all_done else "in_progress"
                    await NotificationService.notify_group_status_changed(
                        bot, grp_tg_id, task, old_status, label, user.full_name,
                    )
        except Exception as e:
            logger.warning(f"task_complete guruh notification xatosi: {e}")

    return web.json_response({"ok": True, "status": asg.status, "all_done": all_done})


async def api_task_delete(request):
    """Vazifani o'chirish — faqat YARATUVCHI o'z vazifasini o'chira oladi."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid task_id"}, status=400)

    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        if task.creator_id != user.id:
            return web.json_response(
                {"error": "Faqat vazifa yaratuvchisi o'chira oladi"}, status=403,
            )
        title = task.title
        await session.delete(task)
        await session.commit()
        logger.info(f"User {user.id} ({user.full_name}) deleted task {task_id} ({title!r})")
    return web.json_response({"ok": True, "deleted": task_id})


async def api_upload_attachment(request):
    """Vazifaga fayl/rasm yuklash (multipart)"""
    task_id = int(request.match_info["task_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    reader = await request.multipart()
    comment_text = None
    field = await reader.next()
    # comment_text oldin kelishi mumkin
    if field and field.name == "comment":
        comment_text = (await field.read(decode=True)).decode("utf-8", errors="replace").strip()[:2000]
        field = await reader.next()
    if not field or field.name != "file":
        raise web.HTTPBadRequest(text=json.dumps({"error": "Fayl yo'q"}))

    filename = field.filename or "file"
    safe_name = f"{task_id}_{int(datetime.now(_UTC).timestamp())}_{filename.replace('/', '_')[:120]}"
    file_path = ATTACH_DIR / safe_name
    MAX_SIZE = 100 * 1024 * 1024  # 100 MB
    size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await field.read_chunk(size=65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SIZE:
                f.close()
                file_path.unlink(missing_ok=True)
                raise web.HTTPBadRequest(text=json.dumps({"error": "Fayl 100 MB dan katta bo'lmasin"}))
            f.write(chunk)

    mime = field.headers.get("Content-Type", "application/octet-stream")
    if mime.startswith("image/"):
        ftype = "photo"
    elif mime.startswith("video/"):
        ftype = "video"
    elif mime.startswith("audio/"):
        ftype = "voice"
    else:
        ftype = "document"

    async with get_session() as session:
        att = TaskAttachment(
            task_id=task_id, user_id=user.id,
            file_type=ftype, file_name=filename,
            file_url=f"/uploads/{safe_name}", file_size=size, mime_type=mime,
        )
        session.add(att)
        if comment_text:
            session.add(TaskComment(task_id=task_id, user_id=user.id, content=comment_text))
        session.add(TaskHistory(
            task_id=task_id, user_id=user.id, action="attachment_added",
            new_value={"file_name": filename, "file_type": ftype,
                       "comment": comment_text or ""},
        ))
        await session.flush()
        att_id = att.id

    return web.json_response({
        "ok": True,
        "attachment": {
            "id": att_id, "file_type": ftype, "file_name": filename,
            "file_url": f"/uploads/{safe_name}", "file_size": size, "mime_type": mime,
        }
    })


async def _notify_workflow_participants(bot, step, actor_user, kind: str, content: str = None, file_info: dict = None):
    """Workflow qadami uchun yangi izoh/fayl qo'shilganda hammaga xabar."""
    if not bot:
        return
    try:
        async with get_session() as session:
            # Step → task → all participants (creator + assignee users)
            task_res = await session.execute(select(Task).where(Task.id == step.task_id))
            task = task_res.scalar_one_or_none()
            if not task:
                return
            # All workflow step assignees
            steps_res = await session.execute(
                select(TaskStep.assignee_user_id).where(TaskStep.task_id == step.task_id)
            )
            assignee_ids = set(r[0] for r in steps_res.all() if r[0])
            assignee_ids.add(task.creator_id)
            # Kuzatuvchilarni ham qo'shamiz (TaskAssignment is_responsible=False)
            obs_res = await session.execute(
                select(TaskAssignment.user_id).where(TaskAssignment.task_id == step.task_id)
            )
            for r in obs_res.all():
                if r[0]:
                    assignee_ids.add(r[0])
            assignee_ids.discard(actor_user.id)  # actorga xabar bermaymiz

            from pathlib import Path as _Path
            from aiogram.types import (
                FSInputFile as _FSInput,
                InlineKeyboardButton as _IKB,
                InlineKeyboardMarkup as _IKM,
            )
            _wf_kb = _IKM(inline_keyboard=[
                [_IKB(text="🔍 Batafsil ko'rish", callback_data=f"wf:view:{step.task_id}")]
            ])

            for uid in assignee_ids:
                u = await session.get(User, uid)
                if not u or not u.telegram_id:
                    continue
                actor_mention = f"@{actor_user.username}" if actor_user.username else actor_user.full_name
                if kind == "comment":
                    msg = (
                        f"💬 <b>Workflow qadamiga izoh</b>\n\n"
                        f"📋 Vazifa: <b>{task.title}</b>\n"
                        f"🪜 Qadam: <b>{step.title}</b>\n"
                        f"👤 <b>{actor_mention}</b> yozdi:\n\n"
                        f"<i>{content}</i>"
                    )
                    try:
                        await bot.send_message(u.telegram_id, msg, reply_markup=_wf_kb)
                    except Exception:
                        pass
                elif kind == "file" and file_info:
                    caption = (
                        f"📎 <b>Workflow qadamiga fayl yuklandi</b>\n\n"
                        f"📋 Vazifa: <b>{task.title}</b>\n"
                        f"🪜 Qadam: <b>{step.title}</b>\n"
                        f"👤 Yukladi: <b>{actor_mention}</b>\n"
                        f"📄 Fayl: <code>{file_info.get('file_name', 'fayl')}</code>"
                    )
                    fpath = file_info.get("file_path")
                    ftype = file_info.get("file_type", "document")
                    sent = False
                    if fpath and _Path(fpath).exists():
                        try:
                            fs = _FSInput(fpath)
                            if ftype == "photo":
                                await bot.send_photo(u.telegram_id, fs, caption=caption, reply_markup=_wf_kb)
                            elif ftype == "video":
                                await bot.send_video(u.telegram_id, fs, caption=caption, reply_markup=_wf_kb)
                            else:
                                await bot.send_document(u.telegram_id, fs, caption=caption, reply_markup=_wf_kb)
                            sent = True
                        except Exception:
                            pass
                    if not sent:
                        try:
                            await bot.send_message(u.telegram_id, caption, reply_markup=_wf_kb)
                        except Exception:
                            pass
    except Exception as e:
        logger.warning(f"Workflow notify xatosi: {e}")


async def api_workflow_step_comment(request):
    """Workflow qadamiga izoh qo'shish — barcha qatnashganlarga xabar yuboriladi."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        step_id = int(request.match_info["step_id"])
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid request"}, status=400)
    content = (body.get("content") or "").strip()
    if len(content) < 1:
        return web.json_response({"error": "matn bo'sh"}, status=400)
    content = content[:4000]

    async with get_session() as session:
        step = await session.get(TaskStep, step_id)
        if not step:
            return web.json_response({"error": "step not found"}, status=404)
        # Ruxsat: qadam egasi yoki workflow yaratuvchisi yoki boshqa qadam egasi
        task = await session.get(Task, step.task_id)
        if not task:
            return web.json_response({"error": "task not found"}, status=404)
        # Tekshiruv — kim izoh yoza oladi
        if user.id != task.creator_id and user.id != step.assignee_user_id:
            other_step = await session.execute(
                select(TaskStep.id).where(
                    TaskStep.task_id == step.task_id,
                    TaskStep.assignee_user_id == user.id,
                )
            )
            if not other_step.scalar_one_or_none():
                return web.json_response({"error": "forbidden"}, status=403)
        c = TaskStepComment(step_id=step_id, user_id=user.id, content=content)
        session.add(c)
        await session.commit()
        c_id = c.id

    # Barcha qatnashganlarga xabar
    bot = request.app.get("bot")
    await _notify_workflow_participants(bot, step, user, "comment", content=content)

    return web.json_response({"ok": True, "id": c_id})


async def api_workflow_step_upload(request):
    """Workflow qadamiga fayl yuklash (multipart) — barcha qatnashganlarga xabar."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        step_id = int(request.match_info["step_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid step_id"}, status=400)

    # Ruxsat tekshiruvi
    async with get_session() as session:
        step = await session.get(TaskStep, step_id)
        if not step:
            return web.json_response({"error": "step not found"}, status=404)
        task = await session.get(Task, step.task_id)
        if not task:
            return web.json_response({"error": "task not found"}, status=404)
        if user.id != task.creator_id and user.id != step.assignee_user_id:
            other_step = await session.execute(
                select(TaskStep.id).where(
                    TaskStep.task_id == step.task_id,
                    TaskStep.assignee_user_id == user.id,
                )
            )
            if not other_step.scalar_one_or_none():
                return web.json_response({"error": "forbidden"}, status=403)

    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        return web.json_response({"error": "no file"}, status=400)

    filename = field.filename or "file"
    safe_name = f"wfstep_{step_id}_{int(datetime.now(_UTC).timestamp())}_{filename.replace('/', '_')[:120]}"
    file_path = ATTACH_DIR / safe_name
    MAX_SIZE = 100 * 1024 * 1024
    size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await field.read_chunk(size=65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SIZE:
                f.close()
                file_path.unlink(missing_ok=True)
                return web.json_response({"error": "fayl 100MB dan katta"}, status=400)
            f.write(chunk)

    mime = field.headers.get("Content-Type", "application/octet-stream")
    if mime.startswith("image/"):
        ftype = "photo"
    elif mime.startswith("video/"):
        ftype = "video"
    elif mime.startswith("audio/"):
        ftype = "voice"
    else:
        ftype = "document"

    file_url = f"/uploads/{safe_name}"

    async with get_session() as session:
        att = TaskStepAttachment(
            step_id=step_id, user_id=user.id,
            file_type=ftype, file_name=filename,
            file_url=file_url, file_size=size, mime_type=mime,
        )
        session.add(att)
        await session.commit()
        att_id = att.id
        # step va task ni refresh qilamiz
        step = await session.get(TaskStep, step_id)

    bot = request.app.get("bot")
    await _notify_workflow_participants(
        bot, step, user, "file",
        file_info={
            "file_path": str(file_path),
            "file_type": ftype,
            "file_name": filename,
        },
    )

    return web.json_response({
        "ok": True,
        "attachment": {
            "id": att_id, "file_type": ftype, "file_name": filename,
            "file_url": file_url, "file_size": size,
        }
    })


async def api_ai_confirm_task(request):
    """AI tomonidan taklif qilingan vazifani foydalanuvchi tasdiqlaganda yaratadi."""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    title = (body.get("title") or "").strip()
    desc = (body.get("description") or "").strip()
    prio_str = body.get("priority") or "medium"
    dl_str = body.get("deadline")
    company_id_str = body.get("company_id") or "personal"

    if not title or not desc or not dl_str:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Nom, tavsif va deadline majburiy"}))

    priority_map = {"low": Priority.LOW, "medium": Priority.MEDIUM, "high": Priority.HIGH, "urgent": Priority.URGENT}
    priority = priority_map.get(prio_str, Priority.MEDIUM)

    deadline = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            deadline = datetime.strptime(dl_str, fmt)
            break
        except ValueError:
            continue
    if not deadline:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Deadline formati noto'g'ri"}))

    c_id = None
    if company_id_str and company_id_str not in ("personal", "all"):
        try:
            c_id = int(company_id_str)
        except (ValueError, TypeError):
            c_id = None

    async with get_session() as session:
        task = Task(
            title=title, description=desc, priority=priority, deadline=deadline,
            creator_id=user.id, company_id=c_id, status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()
        session.add(TaskAssignment(task_id=task.id, user_id=user.id))
        session.add(TaskHistory(
            task_id=task.id, user_id=user.id, action="created",
            new_value={"title": title, "source": "ai_chat_confirmed"},
        ))
        new_task_id = task.id
        await session.commit()

    # Workspace nomi
    ws_label = "👤 Shaxsiy"
    if c_id:
        try:
            async with get_session() as _s2:
                co = await _s2.execute(select(Company).where(Company.id == c_id))
                co_obj = co.scalar_one_or_none()
                if co_obj:
                    ws_label = f"🏢 {co_obj.name}"
        except Exception:
            pass

    pnames = {"low": "🟢 Past", "medium": "🟡 O'rta", "high": "🟠 Yuqori", "urgent": "🔴 Muhim"}
    pn = pnames.get(prio_str, "🟡 O'rta")
    dl_fmt = deadline.strftime("%d.%m.%Y %H:%M")

    msg = (
        "✨ <b>Vazifa yaratildi!</b>\n\n"
        f"🆔 <b>ID:</b> #{new_task_id}\n"
        f"📌 <b>Nomi:</b> {_he(title)}\n"
        f"📝 <b>Tavsif:</b> {_he(desc)}\n"
        f"⚡ <b>Muhimlik:</b> {pn}\n"
        f"⏰ <b>Deadline:</b> {dl_fmt}\n"
        f"📁 <b>Workspace:</b> {_he(ws_label)}\n"
        f"📊 <b>Status:</b> 🆕 Yangi\n\n"
        "✅ Vazifa ro'yxatingizga qo'shildi!"
    )

    return web.json_response({
        "ok": True,
        "task_id": new_task_id,
        "text": msg,
    })


_AVATAR_CACHE: dict = {}  # telegram_id -> (bytes, mime, ts)
_AVATAR_TTL = 6 * 3600  # 6 soat


async def api_get_avatar(request):
    """Foydalanuvchining Telegram profil rasmini qaytaradi (proxy)."""
    import time as _time
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    bot = request.app.get("bot")
    if not bot:
        raise web.HTTPNotFound(text="no bot")

    tg_id = user.telegram_id
    now = _time.time()
    cached = _AVATAR_CACHE.get(tg_id)
    if cached and (now - cached[2]) < _AVATAR_TTL:
        data, mime, _ts = cached
        return web.Response(body=data, content_type=mime, headers={
            "Cache-Control": "private, no-store",
        })

    try:
        photos = await bot.get_user_profile_photos(tg_id, limit=1)
        if not photos.total_count or not photos.photos:
            raise web.HTTPNotFound(text="no photo")
        # Eng katta o'lchamni olamiz
        sizes = photos.photos[0]
        biggest = max(sizes, key=lambda p: (p.width or 0) * (p.height or 0))
        file = await bot.get_file(biggest.file_id)
        bio = await bot.download_file(file.file_path)
        data = bio.read() if hasattr(bio, "read") else bytes(bio)
        mime = "image/jpeg"
        if file.file_path and file.file_path.lower().endswith(".png"):
            mime = "image/png"
        _AVATAR_CACHE[tg_id] = (data, mime, now)
        return web.Response(body=data, content_type=mime, headers={
            "Cache-Control": "private, no-store",
        })
    except web.HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Avatar olishda xato (tg_id={tg_id}): {e}")
        raise web.HTTPNotFound(text="no photo")


# ===== WORKFLOWS (ketma-ket vazifalar) =====

async def api_get_workflows(request):
    """Foydalanuvchi ko'rishi mumkin bo'lgan workflow vazifalar ro'yxati.
    - Yaratuvchi men, yoki
    - Bironta qadam menga biriktirilgan
    Har biri uchun: qadamlar, joriy aktiv qadam, statistika.
    """
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"workflows": []})

    async with get_session() as session:
        # Workflows: faqat task_steps mavjud bo'lgan vazifalar
        rows = await session.execute(
            select(Task).join(TaskStep, TaskStep.task_id == Task.id)
            .where(
                (TaskStep.assignee_user_id == user.id) | (Task.creator_id == user.id)
            ).distinct().order_by(Task.created_at.desc())
        )
        tasks_list = list(rows.scalars())

        result = []
        for t in tasks_list:
            sr = await session.execute(
                select(TaskStep).where(TaskStep.task_id == t.id)
                .order_by(TaskStep.order_index)
            )
            steps = list(sr.scalars())
            done_n = sum(1 for s in steps if s.status == "done")
            cur = next((s for s in steps if s.status == "active"), None)

            # ijrochilar nomlari
            user_ids = list({s.assignee_user_id for s in steps})
            ur = await session.execute(select(User).where(User.id.in_(user_ids))) if user_ids else None
            uname = {}
            if ur:
                for u in ur.scalars():
                    uname[u.id] = u.full_name or u.username or f"#{u.id}"

            current_user_name = uname.get(cur.assignee_user_id) if cur else None
            current_user_id = cur.assignee_user_id if cur else None

            # Navbati kelmagan qadamlar uchun taxminiy sanalar
            _proj = _project_step_dates(steps)

            steps_payload = []
            for s in steps:
                # Izohlar
                cr = await session.execute(
                    select(TaskStepComment).where(TaskStepComment.step_id == s.id)
                    .order_by(TaskStepComment.created_at)
                )
                comments = []
                for c in cr.scalars():
                    cu = uname.get(c.user_id)
                    if not cu:
                        _u = await session.get(User, c.user_id)
                        cu = (_u.full_name or _u.username or f"#{c.user_id}") if _u else "?"
                        uname[c.user_id] = cu
                    comments.append({
                        "id": c.id,
                        "user": cu,
                        "user_id": c.user_id,
                        "content": c.content,
                        "created_at": c.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M"),
                    })
                # Fayllar
                ar = await session.execute(
                    select(TaskStepAttachment).where(TaskStepAttachment.step_id == s.id)
                    .order_by(TaskStepAttachment.created_at)
                )
                atts = []
                for a in ar.scalars():
                    atts.append({
                        "id": a.id,
                        "file_type": a.file_type,
                        "file_url": a.file_url,
                        "file_name": a.file_name,
                        "file_size": a.file_size,
                        "mime_type": a.mime_type,
                        "user_id": a.user_id,
                        "user_name": uname.get(a.user_id, "?"),
                        "created_at": a.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if a.created_at else "",
                    })

                steps_payload.append({
                    "id": s.id,
                    "order": s.order_index + 1,
                    "title": s.title,
                    "status": s.status,
                    "assignee_id": s.assignee_user_id,
                    "assignee_name": uname.get(s.assignee_user_id, "?"),
                    "is_me": (s.assignee_user_id == user.id),
                    "deadline": s.deadline.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if s.deadline else None,
                    "duration_days": getattr(s, "duration_days", None),
                    "projected_deadline": (
                        _proj[s.id].astimezone(_TZ).strftime("%d.%m.%Y %H:%M")
                        if s.id in _proj else None
                    ),
                    "started_at": s.started_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if s.started_at else None,
                    "completed_at": s.completed_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if s.completed_at else None,
                    "note": s.note,
                    "comments": comments,
                    "attachments": atts,
                })

            # vaqt — joriy qadam qancha vaqt turibdi
            stuck_minutes = None
            if cur and cur.started_at:
                stuck_minutes = int((datetime.now(_UTC) - cur.started_at.astimezone(_UTC)).total_seconds() // 60)

            result.append({
                "task_id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "creator_id": t.creator_id,
                "is_creator": (t.creator_id == user.id),
                "total_steps": len(steps),
                "done_steps": done_n,
                "progress_percent": int(done_n * 100 / len(steps)) if steps else 0,
                "current_step_order": (cur.order_index + 1) if cur else None,
                "current_step_title": cur.title if cur else None,
                "current_assignee_id": current_user_id,
                "current_assignee_name": current_user_name,
                "current_is_me": (cur.assignee_user_id == user.id) if cur else False,
                "stuck_minutes": stuck_minutes,
                "steps": steps_payload,
                "created_at": t.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M"),
            })

        return web.json_response({"workflows": result})


async def api_workflow_step_start(request):
    """Qadamni boshlash — pending → active, history ga yozish"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid task_id"}, status=400)

    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return web.json_response({"error": "not found"}, status=404)

        # Hozirgi qadamni topish (pending yoki active)
        result = await session.execute(
            select(TaskStep).where(
                (TaskStep.task_id == task_id) &
                ((TaskStep.status == "pending") | (TaskStep.status == "active"))
            ).order_by(TaskStep.order_index)
        )
        cur = result.scalars().first()

        if not cur or cur.assignee_user_id != user.id:
            return web.json_response({"error": "forbidden"}, status=403)

        if cur.status == "pending":
            _activate_step(cur, datetime.now(_UTC))
            await session.commit()

            # History ga yozish
            hist = TaskHistory(
                task_id=task_id,
                user_id=user.id,
                action="step_started",
                new_value={"step_id": cur.id, "step_number": cur.order_index + 1, "step_title": cur.title}
            )
            session.add(hist)
            await session.commit()

        return web.json_response({"ok": True, "status": cur.status})


async def api_workflow_step_done(request):
    """Joriy active qadamni tugatish — comment va status bilan."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Auth required"}, status=401)

    task_id = int(request.match_info["task_id"])
    body = await request.json() if request.body_exists else {}
    if not isinstance(body, dict):
        body = {}
    comment = (body.get("comment") or body.get("note") or "").strip()[:2000] or None
    new_status = (body.get("status") or "done").strip().lower()
    if new_status not in ("done", "blocked"):
        new_status = "done"

    async with get_session() as session:
        sr = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id)
            .order_by(TaskStep.order_index)
        )
        steps = list(sr.scalars())
        if not steps:
            return web.json_response({"error": "Workflow topilmadi"}, status=404)

        cur = next((s for s in steps if s.status == "active"), None)
        if not cur:
            return web.json_response({"error": "Aktiv qadam yo'q"}, status=400)
        if cur.assignee_user_id != user.id:
            return web.json_response({"error": "Bu qadam sizga biriktirilmagan"}, status=403)

        from datetime import datetime as _dt
        # Izoh saqlash
        if comment:
            session.add(TaskStepComment(
                step_id=cur.id, user_id=user.id, content=comment,
            ))
            cur.note = comment[:500]
        cur.status = new_status
        cur.completed_at = _dt.utcnow() if new_status == "done" else None

        nxt = next((s for s in steps if s.order_index == cur.order_index + 1), None)
        bot = request.app.get("bot")
        finished = False

        if new_status == "done" and nxt:
            _activate_step(nxt, _dt.utcnow())
            # History: current step done
            hist = TaskHistory(
                task_id=task_id, user_id=user.id, action="step_done",
                new_value={"step_id": cur.id, "step_number": cur.order_index + 1}
            )
            session.add(hist)
            await session.commit()
            if bot:
                try:
                    nu = await session.get(User, nxt.assignee_user_id)
                    if nu and nu.telegram_id:
                        msg = (
                            f"🔔 <b>Sizning navbatingiz keldi!</b>\n\n"
                            f"📋 Vazifa #{task_id}\n"
                            f"🪜 Qadam {nxt.order_index+1}: <b>{nxt.title}</b>\n\n"
                            f"Oldingi qadam ({user.full_name}):\n"
                        )
                        if comment:
                            msg += f"💬 <i>{comment[:300]}</i>\n\n"
                        msg += f"Tugatgach: Mini App'da yoki <code>/step {task_id}</code>"
                        await bot.send_message(nu.telegram_id, msg)
                except Exception as e:
                    logger.warning(f"WF API notify: {e}")
        elif new_status == "done" and not nxt:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.DONE
                task.completed_at = _dt.utcnow()
            finished = True
            await session.commit()
            if bot:
                try:
                    if task and task.creator_id != user.id:
                        creator = await session.get(User, task.creator_id)
                        if creator and creator.telegram_id:
                            await bot.send_message(
                                creator.telegram_id,
                                f"🎉 Workflow vazifa <b>{task.title}</b> (#{task_id}) tugatildi!"
                            )
                except Exception:
                    pass
        else:  # blocked
            await session.commit()
            if bot:
                try:
                    task = await session.get(Task, task_id)
                    if task and task.creator_id != user.id:
                        creator = await session.get(User, task.creator_id)
                        if creator and creator.telegram_id:
                            blk = (
                                f"⚠️ <b>Workflow to'xtatildi!</b>\n\n"
                                f"📋 Vazifa #{task_id}: {task.title}\n"
                                f"🪜 Qadam {cur.order_index+1} ({user.full_name}) — blocked"
                            )
                            if comment:
                                blk += f"\n\n💬 Sababi: <i>{comment[:400]}</i>"
                            await bot.send_message(creator.telegram_id, blk)
                except Exception:
                    pass

        return web.json_response({
            "ok": True,
            "status": new_status,
            "finished": finished,
            "next_step": {
                "title": nxt.title,
                "assignee": (await session.get(User, nxt.assignee_user_id)).full_name
                            if nxt and nxt.assignee_user_id else None
            } if (nxt and new_status == "done") else None,
        })


async def api_get_i18n(request):
    """Foydalanuvchining tanlangan tilidagi barcha tarjimalar.
    Mini-app initial yuklanishida shu yerdan UI matnlarini oladi.
    """
    from i18n import get_all, SUPPORTED_LANGS

    user = await get_user_from_request(request)
    if not user:
        # Telegram init data bo'lmasa default uz qaytaradi
        return web.json_response({
            "lang": "uz",
            "translations": get_all("uz"),
            "supported": list(SUPPORTED_LANGS),
        })

    lang = (user.language or "uz").lower()
    return web.json_response({
        "lang": lang,
        "translations": get_all(lang),
        "supported": list(SUPPORTED_LANGS),
    })


async def api_set_language(request):
    """Mini-app dan tilni o'zgartirish — bot va mini-app ikkalasi sinxronlanadi."""
    from i18n import SUPPORTED_LANGS, get_all

    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    lang = (body.get("lang") or "").lower().strip()
    if lang not in SUPPORTED_LANGS:
        return web.json_response({"error": "unsupported language"}, status=400)

    # DB-ga yozamiz
    async with get_session() as session:
        db_user = await session.get(User, user.id)
        if db_user is None:
            return web.json_response({"error": "user not found"}, status=404)
        db_user.language = lang

    return web.json_response({
        "ok": True,
        "lang": lang,
        "translations": get_all(lang),
    })


async def api_create_workflow(request):
    """Mini App'dan workflow yaratish — task + steps"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    title = body.get("title", "").strip()
    if not title or len(title) < 3:
        return web.json_response({"error": "title too short"}, status=400)

    description = body.get("description")
    priority_str = body.get("priority", "medium")
    deadline_str = body.get("deadline")
    company_id_str = body.get("company_id")
    steps_raw = body.get("steps") or []

    if not steps_raw:
        return web.json_response({"error": "steps required"}, status=400)

    try:
        priority = Priority(priority_str)
    except ValueError:
        priority = Priority.MEDIUM

    deadline = None
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            # timezone info saqlash — PostgreSQL TZ=Asia/Tashkent uchun muhim
        except (ValueError, TypeError):
            pass

    async with get_session() as session:
        c_id = None
        if company_id_str and company_id_str != "personal":
            try:
                c_id = int(company_id_str)
            except (ValueError, TypeError):
                pass

        # Create task
        task = Task(
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            creator_id=user.id,
            company_id=c_id,
            status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()

        # Create steps
        for idx, step_data in enumerate(steps_raw):
            step_title = (step_data.get("title") or "").strip()
            assignee_id = step_data.get("assignee_user_id")

            if not step_title or not assignee_id:
                continue

            # Per-step deadline
            step_dl = None
            step_dl_str = step_data.get("deadline")
            if step_dl_str:
                try:
                    step_dl = datetime.fromisoformat(step_dl_str.replace("Z", "+00:00"))
                    step_dl = step_dl.replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            # NISBIY MUDDAT — «N kun»; qadam navbati kelganda hisoblanadi
            try:
                step_dur = int(step_data.get("duration_days") or 0) or None
            except (ValueError, TypeError):
                step_dur = None

            step = TaskStep(
                task_id=task.id,
                title=step_title,
                order_index=idx,
                assignee_user_id=assignee_id,
                deadline=step_dl,
                duration_days=step_dur,
                status="pending",
            )
            session.add(step)

        # History
        session.add(TaskHistory(
            task_id=task.id,
            user_id=user.id,
            action="workflow_created",
            new_value={
                "title": title,
                "steps_count": len(steps_raw),
                "priority": priority_str
            }
        ))

        await session.commit()

        return web.json_response({
            "ok": True,
            "task_id": task.id,
            "title": title,
            "steps_count": len(steps_raw)
        })


async def api_get_task_chart(request):
    """Task uchun vaqt/aktivlik statistikasi — kim nechi soat ketqazgani."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        task_id = int(request.match_info["task_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid task_id"}, status=400)

    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        if not await _user_can_access_task(session, user, task):
            return web.json_response({"error": "forbidden"}, status=403)

        now = datetime.now(_UTC)

        def _hrs(delta):
            return round(delta.total_seconds() / 3600.0, 2)

        def _aware(dt):
            if dt is None:
                return None
            return dt if dt.tzinfo else dt.replace(tzinfo=_UTC)

        per_user = {}  # user_id -> {name, hours, source: 'step'|'assignment'}
        task_started_at: Optional[datetime] = None  # in_progress ga kirgan vaqt

        # --- Workflow qadamlari bo'yicha ---
        steps_res = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id)
            .options(selectinload(TaskStep.assignee))
            .order_by(TaskStep.order_index)
        )
        steps = list(steps_res.scalars().all())
        step_chart = []
        for st in steps:
            start = _aware(st.started_at)
            end = _aware(st.completed_at)
            hours = 0.0
            if start and end:
                hours = _hrs(end - start)
            elif start and st.status == "active":
                hours = _hrs(now - start)
            # attach counts
            cmt_res = await session.execute(
                select(func.count()).select_from(TaskStepComment)
                .where(TaskStepComment.step_id == st.id)
            )
            att_res = await session.execute(
                select(func.count()).select_from(TaskStepAttachment)
                .where(TaskStepAttachment.step_id == st.id)
            )
            step_chart.append({
                "order": st.order_index + 1,
                "title": st.title,
                "status": st.status,
                "assignee": st.assignee.full_name if st.assignee else "—",
                "assignee_id": st.assignee_user_id,
                "hours": hours,
                "started_at": st.started_at.isoformat() if st.started_at else None,
                "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                "comments_count": int(cmt_res.scalar() or 0),
                "attachments_count": int(att_res.scalar() or 0),
            })
            if hours > 0 and st.assignee_user_id:
                uid = st.assignee_user_id
                if uid not in per_user:
                    per_user[uid] = {
                        "user_id": uid,
                        "name": st.assignee.full_name if st.assignee else f"User#{uid}",
                        "hours": 0.0,
                    }
                per_user[uid]["hours"] += hours

        # --- Oddiy taskAssignment bo'yicha (agar step yo'q bo'lsa) ---
        if not steps:
            asg_res = await session.execute(
                select(TaskAssignment).where(TaskAssignment.task_id == task_id)
                .options(selectinload(TaskAssignment.user))
            )
            asg_list = list(asg_res.scalars().all())

            # Per-user aniq vaqt (started_at → completed_at / duration_seconds)
            any_timed = any(a.duration_seconds and a.duration_seconds > 0 for a in asg_list)

            if any_timed:
                # Yangi aniq vaqt kuzatuvi mavjud
                for a in asg_list:
                    uid = a.user_id
                    hours = 0.0
                    if a.duration_seconds and a.duration_seconds > 0:
                        hours = round(a.duration_seconds / 3600.0, 2)
                    elif a.started_at:
                        end = _aware(a.completed_at) or now
                        hours = _hrs(end - _aware(a.started_at))
                    if uid not in per_user:
                        per_user[uid] = {
                            "user_id": uid,
                            "name": a.user.full_name if a.user else f"User#{uid}",
                            "hours": 0.0,
                            "duration_seconds": 0,
                        }
                    per_user[uid]["hours"] += max(hours, 0.0)
                    per_user[uid]["duration_seconds"] = per_user[uid].get("duration_seconds", 0) + (a.duration_seconds or 0)
            else:
                # Eski usul: task history dan in_progress vaqtini topamiz
                hist_res = await session.execute(
                    select(TaskHistory).where(
                        TaskHistory.task_id == task_id,
                        TaskHistory.action == "status_changed",
                    )
                    .order_by(TaskHistory.created_at.asc())
                )
                hist_entries = list(hist_res.scalars().all())
                task_done_at: Optional[datetime] = None
                for h in hist_entries:
                    nv = h.new_value or {}
                    if nv.get("status") == "in_progress" and task_started_at is None:
                        task_started_at = _aware(h.created_at)
                    if nv.get("status") in ("done", "cancelled") and task_done_at is None:
                        task_done_at = _aware(h.created_at)

                for a in asg_list:
                    start = task_started_at or _aware(a.assigned_at)
                    end = task_done_at or now
                    hours = _hrs(end - start) if start else 0.0
                    uid = a.user_id
                    if uid not in per_user:
                        per_user[uid] = {
                            "user_id": uid,
                            "name": a.user.full_name if a.user else f"User#{uid}",
                            "hours": 0.0,
                            "duration_seconds": 0,
                        }
                    per_user[uid]["hours"] += max(hours, 0.0)

        # --- Aktivlik: comment va attachment countlari kim tomonidan yuborilgan ---
        cm_res = await session.execute(
            select(TaskComment.user_id, func.count()).where(TaskComment.task_id == task_id)
            .group_by(TaskComment.user_id)
        )
        comment_counts = {uid: int(cnt) for uid, cnt in cm_res.all()}
        at_res = await session.execute(
            select(TaskAttachment.user_id, func.count()).where(TaskAttachment.task_id == task_id)
            .group_by(TaskAttachment.user_id)
        )
        attach_counts = {uid: int(cnt) for uid, cnt in at_res.all()}

        # Step commentlari va attachmentlarini ham user bo'yicha qo'sh
        if steps:
            step_ids = [s.id for s in steps]
            sc_res = await session.execute(
                select(TaskStepComment.user_id, func.count()).where(TaskStepComment.step_id.in_(step_ids))
                .group_by(TaskStepComment.user_id)
            )
            for uid, cnt in sc_res.all():
                comment_counts[uid] = comment_counts.get(uid, 0) + int(cnt)
            sa_res = await session.execute(
                select(TaskStepAttachment.user_id, func.count()).where(TaskStepAttachment.step_id.in_(step_ids))
                .group_by(TaskStepAttachment.user_id)
            )
            for uid, cnt in sa_res.all():
                attach_counts[uid] = attach_counts.get(uid, 0) + int(cnt)

        # Comment/attachment muallif nomlarini ham per_user ga qo'sh (hours=0 bo'lsa ham ko'rinsin)
        all_uids = set(per_user.keys()) | set(comment_counts.keys()) | set(attach_counts.keys())
        for uid in all_uids:
            if uid not in per_user:
                u = await session.get(User, uid)
                per_user[uid] = {
                    "user_id": uid,
                    "name": u.full_name if u else f"User#{uid}",
                    "hours": 0.0,
                }
            per_user[uid]["comments"] = comment_counts.get(uid, 0)
            per_user[uid]["attachments"] = attach_counts.get(uid, 0)

        users_list = sorted(per_user.values(), key=lambda x: x.get("hours", 0), reverse=True)
        for u in users_list:
            u["hours"] = round(u.get("hours", 0.0), 2)
            u.setdefault("comments", 0)
            u.setdefault("attachments", 0)

        # Umumiy statistika
        total_hours = round(sum(u["hours"] for u in users_list), 2)
        created = _aware(task.created_at) or now
        completed = _aware(task.completed_at)
        lifespan_hours = _hrs((completed or now) - created) if created else 0.0

        return web.json_response({
            "ok": True,
            "task_id": task_id,
            "is_workflow": bool(steps),
            "total_hours": total_hours,
            "lifespan_hours": round(lifespan_hours, 2),
            "task_started_at": task_started_at.isoformat() if task_started_at else None,
            "users": users_list,
            "steps": step_chart,
            "totals": {
                "comments": sum(comment_counts.values()),
                "attachments": sum(attach_counts.values()),
                "steps_done": sum(1 for s in step_chart if s["status"] == "done"),
                "steps_total": len(step_chart),
            },
        })


def _fmt_duration(seconds: Optional[int]) -> str:
    """Sekundlarni o'qiladigan vaqt formatiga o'girish (uz)"""
    if not seconds or seconds <= 0:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds // 60
    if mins < 60:
        return f"{mins}min"
    hours = mins // 60
    rem_mins = mins % 60
    if hours < 24:
        return f"{hours}s {rem_mins}min" if rem_mins else f"{hours} soat"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}kun {rem_hours}soat" if rem_hours else f"{days}kun"


async def api_speed_rating(request):
    """Jamoa tezlik reytingi — kim vazifalarni qanchalik tez bajaradi (avg duration_seconds)."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        company_id = int(request.match_info["company_id"])
    except (ValueError, KeyError):
        return web.json_response({"error": "invalid company_id"}, status=400)

    async with get_session() as session:
        # A'zolik tekshiruvi
        mem_check = await session.execute(
            select(CompanyMember).where(
                and_(CompanyMember.company_id == company_id, CompanyMember.user_id == user.id)
            )
        )
        if not mem_check.scalar_one_or_none():
            return web.json_response({"error": "forbidden"}, status=403)

        # Barcha a'zolar
        members_res = await session.execute(
            select(User, CompanyMember)
            .join(CompanyMember, CompanyMember.user_id == User.id)
            .where(CompanyMember.company_id == company_id)
        )
        members = list(members_res.all())

        now = datetime.now(_UTC)
        rating = []

        for usr, mem in members:
            # Mas'ul sifatida bajarilgan assignmentlar (deadline bilan birga)
            done_res = await session.execute(
                select(
                    TaskAssignment.duration_seconds,
                    TaskAssignment.completed_at,
                    Task.deadline,
                ).select_from(TaskAssignment)
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == usr.id,
                        TaskAssignment.status == "done",
                        TaskAssignment.is_responsible == True,
                        Task.company_id == company_id,
                    )
                )
            )
            done_rows = done_res.all()  # (duration_seconds, completed_at, deadline)

            tasks_done = len(done_rows)
            if tasks_done == 0:
                continue

            # Aniq vaqt o'lchovi bo'lgan qatorlar
            timed = [(dur, ca, dl) for dur, ca, dl in done_rows if dur and dur > 0]
            avg_seconds: Optional[float] = None
            if timed:
                avg_seconds = sum(t[0] for t in timed) / len(timed)

            # Vaqtida bajarilish
            on_time = 0
            late = 0
            for dur_sec, completed_at, deadline in done_rows:
                if deadline and completed_at:
                    ca = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=_UTC)
                    dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=_UTC)
                    if ca <= dl:
                        on_time += 1
                    else:
                        late += 1
            has_deadline = on_time + late
            on_time_rate = round(on_time / has_deadline * 100) if has_deadline else None

            # Reyting bali — adolatli formulali:
            #   on_time_rate (vaqtida bajarish) — eng muhim (50%)
            #   tezlik (speed) — qadamli formula, real ish vaqtlariga moslangan (35%)
            #   hajmi (tasks_done) — ko'p ish bajarganlarga bonus (15%)
            #   suspicion penalty: 30 sekunddan kam vazifalar shubhali deb 25 ball ayriladi
            score = 0.0
            speed_score = None
            if avg_seconds is not None:
                m = avg_seconds / 60.0  # daqiqalar
                if m < 0.5:        speed_score = 50  # 30 sekunddan kam — shubhali
                elif m < 5:        speed_score = 95
                elif m < 30:       speed_score = 90
                elif m < 60:       speed_score = 85       # 1 soatgacha
                elif m < 60 * 4:   speed_score = 80       # 4 soatgacha
                elif m < 60 * 8:   speed_score = 70       # 1 ish kunigacha
                elif m < 60 * 24:  speed_score = 60       # 1 sutkagacha
                elif m < 60 * 24 * 3:   speed_score = 50  # 3 kungacha
                elif m < 60 * 24 * 7:   speed_score = 35  # 1 haftagacha
                elif m < 60 * 24 * 30:  speed_score = 20  # 1 oygacha
                else:                    speed_score = 10
                score += speed_score * 0.35

            # Vaqtida bajarish — eng muhim
            if on_time_rate is not None:
                score += on_time_rate * 0.50
            else:
                # Deadline yo'q tasklar — neytral 60 ball
                score += 60 * 0.50

            # Hajm bonusi — ko'p ishlaganlarga (max 20 task = 100% bonus)
            volume_bonus = min(100, tasks_done * 5)
            score += volume_bonus * 0.15

            # Suspicion penalty — juda qisqa vaqt
            if avg_seconds is not None and avg_seconds < 30:
                score -= 25

            score = max(0, min(100, score))

            rating.append({
                "user_id": usr.id,
                "name": mem.display_name or usr.full_name,
                "tasks_done": tasks_done,
                "timed_tasks": len(timed),
                "avg_seconds": round(avg_seconds) if avg_seconds else None,
                "avg_label": _fmt_duration(int(avg_seconds)) if avg_seconds else "—",
                "on_time_rate": on_time_rate,
                "speed_score": round(speed_score) if speed_score else None,
                "volume_bonus": round(volume_bonus),
                "score": round(score),
            })

        # Tartiblash: ball bo'yicha (yuqori birinchi), keyin tezlik (tez birinchi)
        rating.sort(
            key=lambda x: (-x["score"], x["avg_seconds"] is None, x["avg_seconds"] or 0)
        )

        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rating):
            r["rank"] = i + 1
            r["medal"] = medals[i] if i < 3 else ""

        return web.json_response({"ok": True, "members": rating})


# ===== Admin API =====

def _check_admin(request):
    """Admin tokenni tekshirish (bir nechta hisob qo'llab-quvvatlanadi)"""
    token = request.headers.get("X-Admin-Token", "")
    if token not in _ADMIN_TOKENS:
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "Admin huquqi talab qilinadi"}),
            content_type="application/json",
        )


async def admin_login(request):
    """Admin login"""
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON talab qilinadi"}), content_type="application/json")

    username = body.get("username", "")
    password = body.get("password", "")

    if username in _ADMIN_ACCOUNTS and _ADMIN_ACCOUNTS[username] == password:
        return web.json_response({"ok": True, "token": _admin_token_for(username, password)})
    raise web.HTTPUnauthorized(
        text=json.dumps({"error": "Login yoki parol noto'g'ri"}),
        content_type="application/json",
    )


async def admin_stats(request):
    """Dashboard uchun umumiy statistika"""
    _check_admin(request)
    async with get_session() as session:
        users_count     = (await session.execute(select(func.count(User.id)))).scalar()
        companies_count = (await session.execute(select(func.count(Company.id)))).scalar()
        groups_count    = (await session.execute(select(func.count(Group.id)))).scalar()
        tasks_count     = (await session.execute(select(func.count(Task.id)))).scalar()
        done_count      = (await session.execute(
            select(func.count(Task.id)).where(Task.status == TaskStatus.DONE)
        )).scalar() or 0
        overdue_active  = (await session.execute(
            select(func.count(Task.id)).where(Task.status == TaskStatus.OVERDUE)
        )).scalar() or 0
        # Kechikib bajarilgan vazifalar
        late_done_count = (await session.execute(
            select(func.count(Task.id)).where(
                Task.status == TaskStatus.DONE,
                Task.completed_at.isnot(None),
                Task.deadline.isnot(None),
                Task.completed_at > Task.deadline,
            )
        )).scalar() or 0
        overdue_count = overdue_active + late_done_count

        # Recent users (last 10)
        recent_res = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(10)
        )
        recent_users = []
        for u in recent_res.scalars():
            recent_users.append({
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "full_name": u.full_name,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            })

        # Top companies by member count
        top_res = await session.execute(
            select(
                Company.id,
                Company.name,
                Company.created_at,
                User.username.label("owner_username"),
                User.full_name.label("owner_name"),
                func.count(CompanyMember.id).label("members"),
            )
            .join(User, Company.owner_id == User.id)
            .outerjoin(CompanyMember, CompanyMember.company_id == Company.id)
            .group_by(Company.id, User.username, User.full_name)
            .order_by(func.count(CompanyMember.id).desc())
            .limit(10)
        )
        top_companies = []
        for row in top_res:
            tasks_c = (await session.execute(
                select(func.count(Task.id)).where(Task.company_id == row.id)
            )).scalar()
            top_companies.append({
                "id": row.id,
                "name": row.name,
                "owner_username": row.owner_username,
                "owner_name": row.owner_name,
                "members": row.members,
                "tasks": tasks_c,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

        # ========== KENGAYTIRILGAN STATISTIKA ==========
        from datetime import timedelta as _td

        # Status taqsimoti
        sd_res = await session.execute(
            select(Task.status, func.count(Task.id)).group_by(Task.status)
        )
        status_dist = {}
        for s, c in sd_res.all():
            sv = s.value if hasattr(s, 'value') else str(s)
            status_dist[sv.lower()] = c

        # Priority taqsimoti
        pd_res = await session.execute(
            select(Task.priority, func.count(Task.id)).group_by(Task.priority)
        )
        priority_dist = {}
        for p, c in pd_res.all():
            pv = p.value if hasattr(p, 'value') else str(p)
            priority_dist[pv.lower()] = c

        # Workflow vs Oddiy
        wf_total = (await session.execute(
            select(func.count(func.distinct(TaskStep.task_id)))
        )).scalar() or 0
        wf_vs_simple = {
            "workflow": wf_total,
            "simple": max(0, (tasks_count or 0) - wf_total),
        }

        # 30 kun ichida — har kuni yangi task va done
        now_tz = datetime.now(_TZ)
        days_back = 30
        activity = []
        for d in range(days_back - 1, -1, -1):
            day = now_tz.date() - _td(days=d)
            ds = datetime.combine(day, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            de = ds + _td(days=1)
            created = (await session.execute(
                select(func.count(Task.id)).where(Task.created_at >= ds, Task.created_at < de)
            )).scalar() or 0
            done_day = (await session.execute(
                select(func.count(Task.id)).where(Task.completed_at >= ds, Task.completed_at < de)
            )).scalar() or 0
            activity.append({
                "date": day.strftime("%d.%m"),
                "created": created,
                "done": done_day,
            })

        # Foydalanuvchi o'sishi (30 kun)
        user_growth = []
        for d in range(days_back - 1, -1, -1):
            day = now_tz.date() - _td(days=d)
            ds = datetime.combine(day, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            de = ds + _td(days=1)
            cnt = (await session.execute(
                select(func.count(User.id)).where(User.created_at >= ds, User.created_at < de)
            )).scalar() or 0
            user_growth.append({"date": day.strftime("%d.%m"), "count": cnt})

        # Top users — eng ko'p vazifa bajargan (oxirgi 30 kun)
        since_30 = datetime.now(_UTC) - _td(days=30)
        tu_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(TaskAssignment.id).label("done_cnt"),
            )
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .where(
                TaskAssignment.status == "done",
                TaskAssignment.completed_at >= since_30,
                TaskAssignment.is_responsible.is_(True),
            )
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(TaskAssignment.id).desc())
            .limit(8)
        )
        top_users = [
            {"name": r.full_name, "username": r.username, "done": r.done_cnt}
            for r in tu_res.all()
        ]

        # Faol foydalanuvchilar (oxirgi 7 kun ichida task yaratgan/bajargan)
        since_7 = datetime.now(_UTC) - _td(days=7)
        active_users = (await session.execute(
            select(func.count(func.distinct(User.id)))
            .join(Task, Task.creator_id == User.id)
            .where(Task.created_at >= since_7)
        )).scalar() or 0

        # Top task yaratuvchilar (30 kun)
        tc_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(Task.id).label("created_cnt"),
            )
            .join(Task, Task.creator_id == User.id)
            .where(Task.created_at >= since_30)
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(Task.id).desc())
            .limit(8)
        )
        top_creators = [
            {"name": r.full_name, "username": r.username, "created": r.created_cnt}
            for r in tc_res.all()
        ]

        # Botda eng faol foydalanuvchilar (30 kun) —
        # task yaratish + bajarish + izoh + fayl yuklash birlashtirilgan
        ax_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(func.distinct(Task.id)).label("created_cnt"),
            )
            .join(Task, Task.creator_id == User.id)
            .where(Task.created_at >= since_30)
            .group_by(User.id, User.full_name, User.username)
        )
        created_map = {r.id: (r.full_name, r.username, r.created_cnt) for r in ax_res.all()}

        cm_res = await session.execute(
            select(User.id, User.full_name, User.username, func.count(TaskComment.id).label("c"))
            .join(TaskComment, TaskComment.user_id == User.id)
            .where(TaskComment.created_at >= since_30)
            .group_by(User.id, User.full_name, User.username)
        )
        comment_map = {r.id: (r.full_name, r.username, r.c) for r in cm_res.all()}

        at_res = await session.execute(
            select(User.id, User.full_name, User.username, func.count(TaskAttachment.id).label("c"))
            .join(TaskAttachment, TaskAttachment.user_id == User.id)
            .where(TaskAttachment.created_at >= since_30)
            .group_by(User.id, User.full_name, User.username)
        )
        att_map = {r.id: (r.full_name, r.username, r.c) for r in at_res.all()}

        done_res = await session.execute(
            select(User.id, User.full_name, User.username, func.count(TaskAssignment.id).label("c"))
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .where(
                TaskAssignment.status == "done",
                TaskAssignment.completed_at >= since_30,
            )
            .group_by(User.id, User.full_name, User.username)
        )
        done_map = {r.id: (r.full_name, r.username, r.c) for r in done_res.all()}

        # Birlashtirib hisoblash
        all_ids = set(created_map) | set(comment_map) | set(att_map) | set(done_map)
        active_rows = []
        for uid in all_ids:
            tup = created_map.get(uid) or comment_map.get(uid) or att_map.get(uid) or done_map.get(uid)
            if not tup:
                continue
            name, uname, _ = tup
            cr = created_map.get(uid, (None, None, 0))[2]
            dn = done_map.get(uid, (None, None, 0))[2]
            cm = comment_map.get(uid, (None, None, 0))[2]
            at = att_map.get(uid, (None, None, 0))[2]
            score = cr + dn + cm + at
            active_rows.append({
                "name": name, "username": uname,
                "created": cr, "done": dn, "comments": cm, "attachments": at,
                "score": score,
            })
        active_rows.sort(key=lambda x: x["score"], reverse=True)
        top_active = active_rows[:10]

        # ===== Bugungi faollik =====
        today_local = now_tz.date()
        today_start_utc = datetime.combine(today_local, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
        today_end_utc = today_start_utc + _td(days=1)
        today_created = (await session.execute(
            select(func.count(Task.id)).where(
                Task.created_at >= today_start_utc, Task.created_at < today_end_utc
            )
        )).scalar() or 0
        today_done = (await session.execute(
            select(func.count(Task.id)).where(
                Task.completed_at >= today_start_utc, Task.completed_at < today_end_utc
            )
        )).scalar() or 0
        today_comments = (await session.execute(
            select(func.count(TaskComment.id)).where(
                TaskComment.created_at >= today_start_utc, TaskComment.created_at < today_end_utc
            )
        )).scalar() or 0
        today_files = (await session.execute(
            select(func.count(TaskAttachment.id)).where(
                TaskAttachment.created_at >= today_start_utc, TaskAttachment.created_at < today_end_utc
            )
        )).scalar() or 0

        # ===== O'rtacha bajarish vaqti (soatda) — done bo'lgan tasklar =====
        avg_res = await session.execute(
            select(
                func.avg(
                    func.extract("epoch", Task.completed_at) - func.extract("epoch", Task.created_at)
                )
            ).where(Task.completed_at.isnot(None), Task.created_at.isnot(None))
        )
        avg_seconds = avg_res.scalar()
        avg_completion_hours = round(float(avg_seconds or 0) / 3600, 1) if avg_seconds else 0

        # ===== Workspace bo'yicha taqqoslash =====
        ws_res = await session.execute(
            select(
                Company.id, Company.name,
                func.count(Task.id).label("total"),
            )
            .join(Task, Task.company_id == Company.id)
            .group_by(Company.id, Company.name)
            .order_by(func.count(Task.id).desc())
            .limit(8)
        )
        workspace_comparison = []
        for r in ws_res.all():
            done_c = (await session.execute(
                select(func.count(Task.id)).where(
                    Task.company_id == r.id,
                    Task.status == "done",
                )
            )).scalar() or 0
            overdue_c = (await session.execute(
                select(func.count(Task.id)).where(
                    Task.company_id == r.id,
                    Task.status == "overdue",
                )
            )).scalar() or 0
            workspace_comparison.append({
                "name": r.name,
                "total": r.total,
                "done": done_c,
                "overdue": overdue_c,
                "rate": round(done_c / r.total * 100, 1) if r.total else 0,
            })

        # ===== Kechikib bajarganlar (oxirgi 90 kun) — kim qancha =====
        # TaskAssignment'da completed_at > Task.deadline shartiga moslar
        since_90 = datetime.now(_UTC) - _td(days=90)
        late_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(TaskAssignment.id).label("c"),
            )
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.status == "done",
                TaskAssignment.is_responsible.is_(True),
                TaskAssignment.completed_at.isnot(None),
                Task.deadline.isnot(None),
                TaskAssignment.completed_at > Task.deadline,
                TaskAssignment.completed_at >= since_90,
            )
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(TaskAssignment.id).desc())
            .limit(10)
        )
        top_late_completers = [
            {"user_id": r.id, "name": r.full_name, "username": r.username, "count": r.c}
            for r in late_res.all()
        ]

        # ===== Hozir kechikkan, HALI BAJARILMAGAN vazifalar — kim qancha =====
        # deadline o'tib ketgan, lekin mas'ul hali tugatmagan (ochiq) vazifalar
        _now_ov = datetime.now(_UTC)
        overdue_pending_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(TaskAssignment.id).label("c"),
            )
            .join(TaskAssignment, TaskAssignment.user_id == User.id)
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.is_responsible.is_(True),
                TaskAssignment.status.notin_(["done", "cancelled"]),
                Task.deadline.isnot(None),
                Task.deadline < _now_ov,
                Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
            )
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(TaskAssignment.id).desc())
            .limit(10)
        )
        top_overdue_pending = [
            {"user_id": r.id, "name": r.full_name, "username": r.username, "count": r.c}
            for r in overdue_pending_res.all()
        ]
        total_overdue_pending = sum(x["count"] for x in top_overdue_pending)

        # Jami kechikib yopilgan vazifalar (90 kun)
        total_late_done = (await session.execute(
            select(func.count(Task.id)).where(
                Task.status == "done",
                Task.completed_at.isnot(None),
                Task.deadline.isnot(None),
                Task.completed_at > Task.deadline,
                Task.completed_at >= since_90,
            )
        )).scalar() or 0

        # ===== Hafta kunlari bo'yicha (oxirgi 90 kun) — created vs done =====
        # 0=Du, 6=Ya  (Python weekday)
        weekday_created = [0] * 7
        weekday_done = [0] * 7
        since_90 = datetime.now(_UTC) - _td(days=90)
        wc_res = await session.execute(
            select(
                func.extract("dow", Task.created_at).label("dow"),
                func.count(Task.id),
            )
            .where(Task.created_at >= since_90)
            .group_by(func.extract("dow", Task.created_at))
        )
        for r in wc_res.all():
            # Postgres dow: 0=Sun..6=Sat → biz Du=0..Ya=6 ga aylantirib qo'yamiz
            pg = int(r.dow)
            idx = (pg + 6) % 7
            weekday_created[idx] = int(r[1])
        wd_res = await session.execute(
            select(
                func.extract("dow", Task.completed_at).label("dow"),
                func.count(Task.id),
            )
            .where(Task.completed_at >= since_90)
            .group_by(func.extract("dow", Task.completed_at))
        )
        for r in wd_res.all():
            pg = int(r.dow)
            idx = (pg + 6) % 7
            weekday_done[idx] = int(r[1])

        # Status summary (in_progress, new, review)
        in_progress_count = status_dist.get("in_progress", 0)
        new_count         = status_dist.get("new", 0)
        review_count      = status_dist.get("review", 0)

        return web.json_response({
            "ok": True,
            "users": users_count,
            "companies": companies_count,
            "groups": groups_count,
            "tasks": tasks_count,
            "done": done_count,
            "overdue": overdue_count,
            "in_progress": in_progress_count,
            "new": new_count,
            "review": review_count,
            "active_users_7d": active_users,
            "completion_rate": round(done_count / tasks_count * 100, 1) if tasks_count else 0,
            "recent_users": recent_users,
            "top_companies": top_companies,
            "status_dist": status_dist,
            "priority_dist": priority_dist,
            "wf_vs_simple": wf_vs_simple,
            "activity_30d": activity,
            "user_growth_30d": user_growth,
            "top_users": top_users,
            "top_creators": top_creators,
            "top_active": top_active,
            "top_late_completers": top_late_completers,
            "total_late_done_90d": total_late_done,
            "top_overdue_pending": top_overdue_pending,
            "total_overdue_pending": total_overdue_pending,
            "today": {
                "created": today_created,
                "done": today_done,
                "comments": today_comments,
                "files": today_files,
            },
            "avg_completion_hours": avg_completion_hours,
            "workspace_comparison": workspace_comparison,
            "weekday_activity": {
                "labels": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"],
                "created": weekday_created,
                "done": weekday_done,
            },
        })


async def admin_users(request):
    """Barcha foydalanuvchilar"""
    _check_admin(request)
    async with get_session() as session:
        res = await session.execute(
            select(User).order_by(User.created_at.desc())
        )
        users = []
        for u in res.scalars():
            co_cnt = (await session.execute(
                select(func.count(CompanyMember.id)).where(CompanyMember.user_id == u.id)
            )).scalar()
            gr_cnt = (await session.execute(
                select(func.count(GroupMember.id)).where(GroupMember.user_id == u.id)
            )).scalar()
            ta_cnt = (await session.execute(
                select(func.count(TaskAssignment.id)).where(TaskAssignment.user_id == u.id)
            )).scalar()
            # Oxirgi faoliyat
            last_hist = (await session.execute(
                select(TaskHistory.action, TaskHistory.created_at)
                .where(TaskHistory.user_id == u.id)
                .order_by(TaskHistory.created_at.desc())
                .limit(1)
            )).one_or_none()
            users.append({
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "full_name": u.full_name,
                "is_banned": u.is_banned,
                "is_hr": u.is_hr,
                "is_feedback_admin": bool(getattr(u, "is_feedback_admin", False)),
                "ai_enabled": bool(getattr(u, "ai_enabled", False)),
                "companies": co_cnt,
                "groups": gr_cnt,
                "tasks": ta_cnt,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_action": last_hist.action if last_hist else None,
                "last_action_at": last_hist.created_at.isoformat() if last_hist else None,
            })
        return web.json_response({"ok": True, "users": users})


async def admin_user_details(request):
    """Foydalanuvchining to'liq profili — barcha ma'lumotlar bir joyda."""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])

    async with get_session() as session:
        u_res = await session.execute(select(User).where(User.id == user_id))
        u = u_res.scalar_one_or_none()
        if not u:
            return web.json_response({"error": "Foydalanuvchi topilmadi"}, status=404)

        # Kompaniyalar
        co_res = await session.execute(
            select(
                Company.id, Company.name,
                CompanyMember.role, CompanyMember.joined_at,
            )
            .join(CompanyMember, CompanyMember.company_id == Company.id)
            .where(CompanyMember.user_id == user_id)
            .order_by(Company.name)
        )
        companies = [{
            "id": r[0], "name": r[1],
            "role": r[2].value if hasattr(r[2], "value") else str(r[2]),
            "joined_at": r[3].isoformat() if r[3] else None,
        } for r in co_res.all()]

        # Guruhlar
        gr_res = await session.execute(
            select(
                Group.id, Group.name, Group.telegram_group_id, Group.is_active,
                GroupMember.role, GroupMember.joined_at,
            )
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.name)
        )
        groups = [{
            "id": r[0], "name": r[1], "telegram_group_id": r[2], "is_active": r[3],
            "role": r[4].value if hasattr(r[4], "value") else str(r[4]),
            "joined_at": r[5].isoformat() if r[5] else None,
        } for r in gr_res.all()]

        # Yaratgan tasklar
        created_res = await session.execute(
            select(Task.id, Task.title, Task.status, Task.deadline, Task.created_at)
            .where(Task.creator_id == user_id)
            .order_by(Task.created_at.desc())
            .limit(50)
        )
        created_tasks = [{
            "id": r[0], "title": r[1],
            "status": r[2].value if hasattr(r[2], "value") else str(r[2]),
            "deadline": r[3].isoformat() if r[3] else None,
            "created_at": r[4].isoformat() if r[4] else None,
        } for r in created_res.all()]

        # Biriktirilgan tasklar (assignmentlar)
        asg_res = await session.execute(
            select(
                Task.id, Task.title, Task.status,
                TaskAssignment.is_responsible, TaskAssignment.status.label("asg_status"),
                Task.deadline,
            )
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(TaskAssignment.user_id == user_id)
            .order_by(Task.created_at.desc())
            .limit(50)
        )
        assigned_tasks = [{
            "id": r[0], "title": r[1],
            "status": r[2].value if hasattr(r[2], "value") else str(r[2]),
            "is_responsible": bool(r[3]),
            "asg_status": r[4],
            "deadline": r[5].isoformat() if r[5] else None,
        } for r in asg_res.all()]

        # Statistika
        created_cnt = (await session.execute(
            select(func.count(Task.id)).where(Task.creator_id == user_id)
        )).scalar() or 0
        # Foydalanuvchi bajargan deb hisoblansin agar:
        # - TaskAssignment.status == "done" (shaxsiy status), YOKI
        # - Task.status == "done" (umumiy vazifa bajarilgan)
        done_cnt = (await session.execute(
            select(func.count(func.distinct(TaskAssignment.id)))
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.user_id == user_id,
                or_(
                    TaskAssignment.status == "done",
                    Task.status == TaskStatus.DONE,
                ),
            )
        )).scalar() or 0
        in_progress_cnt = (await session.execute(
            select(func.count(func.distinct(TaskAssignment.id)))
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.user_id == user_id,
                or_(
                    TaskAssignment.status == "in_progress",
                    Task.status == TaskStatus.IN_PROGRESS,
                ),
                Task.status != TaskStatus.DONE,
            )
        )).scalar() or 0
        comments_cnt = (await session.execute(
            select(func.count(TaskComment.id)).where(TaskComment.user_id == user_id)
        )).scalar() or 0

        # Murojaatlar (yuborilganlar)
        from database.models import Feedback, FeedbackReply
        fb_res = await session.execute(
            select(Feedback.id, Feedback.type, Feedback.status, Feedback.is_anonymous, Feedback.created_at)
            .where(Feedback.user_id == user_id)
            .order_by(Feedback.created_at.desc())
            .limit(20)
        )
        feedbacks = [{
            "id": r[0], "type": r[1], "status": r[2],
            "is_anonymous": bool(r[3]),
            "created_at": r[4].isoformat() if r[4] else None,
        } for r in fb_res.all()]

        # Foydalanuvchi javoblari (HR yo'naltirgan muhokamalarda)
        from database.models import FeedbackDiscussion
        disc_res = await session.execute(
            select(FeedbackDiscussion.id, FeedbackDiscussion.feedback_id,
                   FeedbackDiscussion.status, FeedbackDiscussion.created_at)
            .where(FeedbackDiscussion.target_user_id == user_id)
            .order_by(FeedbackDiscussion.created_at.desc())
            .limit(20)
        )
        discussions = [{
            "id": r[0], "feedback_id": r[1], "status": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        } for r in disc_res.all()]

        # Oxirgi faoliyat (history)
        hist_res = await session.execute(
            select(TaskHistory.action, TaskHistory.created_at, Task.title)
            .join(Task, Task.id == TaskHistory.task_id)
            .where(TaskHistory.user_id == user_id)
            .order_by(TaskHistory.created_at.desc())
            .limit(20)
        )
        recent_activity = [{
            "action": r[0],
            "created_at": r[1].isoformat() if r[1] else None,
            "task_title": r[2],
        } for r in hist_res.all()]

    return web.json_response({
        "ok": True,
        "user": {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "full_name": u.full_name,
            "language": u.language,
            "timezone": u.timezone,
            "is_banned": u.is_banned,
            "is_hr": u.is_hr,
            "is_feedback_admin": bool(getattr(u, "is_feedback_admin", False)),
            "ai_enabled": bool(getattr(u, "ai_enabled", False)),
            "notifications_enabled": u.notifications_enabled,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "updated_at": u.updated_at.isoformat() if u.updated_at else None,
        },
        "stats": {
            "companies_count": len(companies),
            "groups_count": len(groups),
            "created_tasks": created_cnt,
            "assignments_total": len(assigned_tasks),
            "done": done_cnt,
            "in_progress": in_progress_cnt,
            "comments": comments_cnt,
            "feedbacks": len(feedbacks),
            "discussions": len(discussions),
        },
        "companies": companies,
        "groups": groups,
        "created_tasks": created_tasks,
        "assigned_tasks": assigned_tasks,
        "feedbacks": feedbacks,
        "discussions": discussions,
        "recent_activity": recent_activity,
    })


async def admin_delete_user(request):
    """Foydalanuvchini DB'dan butunlay o'chirish (cascade)."""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        u_res = await session.execute(select(User).where(User.id == user_id))
        u = u_res.scalar_one_or_none()
        if not u:
            return web.json_response({"error": "Foydalanuvchi topilmadi"}, status=404)
        # Super admin bot egasini o'chirib bo'lmaydi
        if u.telegram_id in (settings.admin_ids_list or []):
            return web.json_response(
                {"error": "Super adminni o'chirib bo'lmaydi"}, status=403,
            )
        tg = u.telegram_id
        name = u.full_name
        await session.delete(u)
        await session.commit()
        logger.info(f"Admin: deleted user uid={user_id} tg={tg} name={name!r}")
    return web.json_response({"ok": True, "deleted_id": user_id})


async def admin_user_activity(request):
    """Foydalanuvchining so'nggi faoliyati (oxirgi 50 ta)"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        res = await session.execute(
            select(
                TaskHistory.action,
                TaskHistory.created_at,
                TaskHistory.new_value,
                Task.id.label("task_id"),
                Task.title.label("task_title"),
            )
            .join(Task, Task.id == TaskHistory.task_id)
            .where(TaskHistory.user_id == user_id)
            .order_by(TaskHistory.created_at.desc())
            .limit(50)
        )
        rows = res.all()
        activities = []
        for row in rows:
            activities.append({
                "action": row.action,
                "created_at": row.action and row.created_at.isoformat() if row.created_at else None,
                "task_id": row.task_id,
                "task_title": row.task_title,
                "new_value": row.new_value,
            })
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
    return web.json_response({
        "ok": True,
        "activities": activities,
        "user_name": user.full_name if user else str(user_id),
    })


async def admin_companies(request):
    """Barcha workspacelar"""
    _check_admin(request)
    async with get_session() as session:
        res = await session.execute(
            select(
                Company.id,
                Company.name,
                Company.created_at,
                User.username.label("owner_username"),
                User.full_name.label("owner_name"),
                func.count(CompanyMember.id).label("members"),
            )
            .join(User, Company.owner_id == User.id)
            .outerjoin(CompanyMember, CompanyMember.company_id == Company.id)
            .group_by(Company.id, User.username, User.full_name)
            .order_by(Company.created_at.desc())
        )
        companies = []
        for row in res:
            # Get telegram_group_id from linked group if any
            grp_res = await session.execute(
                select(Group.telegram_group_id).where(Group.company_id == row.id).limit(1)
            )
            tg_grp = grp_res.scalar()
            tasks_c = (await session.execute(
                select(func.count(Task.id)).where(Task.company_id == row.id)
            )).scalar()
            companies.append({
                "id": row.id,
                "name": row.name,
                "owner_username": row.owner_username,
                "owner_name": row.owner_name,
                "telegram_group_id": tg_grp,
                "members": row.members,
                "tasks": tasks_c,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return web.json_response({"ok": True, "companies": companies})


async def admin_delete_company(request):
    """Workspace (kompaniya)ni o'chirish — barcha bog'liq vazifa, guruh, a'zo ham CASCADE bilan o'chadi"""
    _check_admin(request)
    company_id = int(request.match_info["company_id"])
    async with get_session() as session:
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        if not company:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Workspace topilmadi"}),
                content_type="application/json",
            )
        name = company.name

        # Hisoblash — admin ko'rsin
        tasks_n   = (await session.execute(
            select(func.count(Task.id)).where(Task.company_id == company_id)
        )).scalar() or 0
        members_n = (await session.execute(
            select(func.count(CompanyMember.id)).where(CompanyMember.company_id == company_id)
        )).scalar() or 0
        groups_n  = (await session.execute(
            select(func.count(Group.id)).where(Group.company_id == company_id)
        )).scalar() or 0

        await session.delete(company)
        await session.commit()
        logger.info(
            f"Admin: company #{company_id} '{name}' deleted "
            f"(tasks={tasks_n}, members={members_n}, groups={groups_n})"
        )
        return web.json_response({
            "ok": True,
            "message": f"'{name}' o'chirildi: {tasks_n} vazifa, {members_n} a'zo, {groups_n} guruh ham olib tashlandi.",
            "deleted": {"tasks": tasks_n, "members": members_n, "groups": groups_n},
        })


async def admin_groups(request):
    """Barcha Telegram guruhlar"""
    _check_admin(request)
    async with get_session() as session:
        res = await session.execute(
            select(
                Group.id,
                Group.name,
                Group.telegram_group_id,
                Group.is_active,
                Group.is_blocked_by_admin,
                Group.created_at,
                Group.company_id,
                User.username.label("owner_username"),
                User.full_name.label("owner_name"),
                func.count(GroupMember.id).label("members"),
            )
            .join(User, Group.owner_id == User.id)
            .outerjoin(GroupMember, GroupMember.group_id == Group.id)
            .group_by(Group.id, User.username, User.full_name)
            .order_by(Group.created_at.desc())
        )
        groups = []
        for row in res:
            tasks_c = (await session.execute(
                select(func.count(Task.id)).where(Task.group_id == row.id)
            )).scalar()
            company_name = None
            if row.company_id:
                co_res = await session.execute(
                    select(Company.name).where(Company.id == row.company_id)
                )
                company_name = co_res.scalar()
            groups.append({
                "id": row.id,
                "name": row.name,
                "telegram_group_id": row.telegram_group_id,
                "is_active": row.is_active,
                "is_blocked_by_admin": bool(row.is_blocked_by_admin),
                "owner_username": row.owner_username,
                "owner_name": row.owner_name,
                "members": row.members,
                "tasks": tasks_c,
                "company_id": row.company_id,
                "company_name": company_name,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
        return web.json_response({"ok": True, "groups": groups})


async def admin_group_block_toggle(request):
    """Guruhda botni bloklash/qaytarish — admin huquqi.
    Bloklanganda bot guruhdan chiqib ketadi va xabarlarga javob bermaydi."""
    _check_admin(request)
    group_id = int(request.match_info["group_id"])
    body = await request.json() if request.body_exists else {}
    block = bool(body.get("block", True))

    async with get_session() as session:
        res = await session.execute(select(Group).where(Group.id == group_id))
        group = res.scalar_one_or_none()
        if not group:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Guruh topilmadi"}),
                content_type="application/json",
            )
        group.is_blocked_by_admin = block
        if block:
            group.is_active = False
        tg_id = group.telegram_group_id
        name = group.name
        await session.commit()

    # Bot guruhdan chiqib ketsin (eng yaxshi UX — admin'lar darhol ko'rishadi)
    left_msg = ""
    if block:
        try:
            tg_bot = request.app.get("bot")
            if tg_bot:
                try:
                    await tg_bot.send_message(
                        tg_id,
                        "🚫 Bu guruhda botdan foydalanish admin tomonidan to'xtatildi. Bot tark etmoqda.",
                    )
                except Exception:
                    pass
                await tg_bot.leave_chat(tg_id)
                left_msg = " Bot guruhdan chiqdi."
        except Exception as e:
            logger.warning(f"Bot leave_chat xatosi: {e}")
            left_msg = f" (Bot chiqib ketishda xato: {e})"

    logger.info(f"Admin: group #{group_id} '{name}' block={block}")
    return web.json_response({
        "ok": True,
        "is_blocked_by_admin": block,
        "message": (f"'{name}' bloklandi.{left_msg}" if block else f"'{name}' bloki olib tashlandi."),
    })


async def admin_group_members(request):
    """Guruh a'zolari ro'yxati"""
    _check_admin(request)
    group_id = int(request.match_info["group_id"])
    async with get_session() as session:
        res = await session.execute(
            select(
                GroupMember.id.label("gm_id"),
                GroupMember.role,
                GroupMember.joined_at,
                User.id.label("user_id"),
                User.full_name,
                User.username,
                User.telegram_id,
                User.is_banned,
            )
            .join(User, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.role, User.full_name)
        )
        members = []
        for row in res:
            task_cnt = (await session.execute(
                select(func.count(TaskAssignment.id))
                .join(Task, Task.id == TaskAssignment.task_id)
                .where(TaskAssignment.user_id == row.user_id, Task.group_id == group_id)
            )).scalar() or 0
            members.append({
                "gm_id": row.gm_id,
                "user_id": row.user_id,
                "full_name": row.full_name,
                "username": row.username,
                "telegram_id": row.telegram_id,
                "is_banned": row.is_banned,
                "role": row.role.value if hasattr(row.role, "value") else str(row.role),
                "tasks": task_cnt,
                "joined_at": row.joined_at.isoformat() if row.joined_at else None,
            })
        group_res = await session.execute(select(Group).where(Group.id == group_id))
        group = group_res.scalar_one_or_none()
        group_name = group.name if group else str(group_id)
    return web.json_response({"ok": True, "members": members, "group_name": group_name})


async def admin_user_groups(request):
    """Foydalanuvchi qaysi guruhlarda borligini ko'rsatish"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        res = await session.execute(
            select(
                Group.id.label("group_id"),
                Group.name.label("group_name"),
                Group.telegram_group_id,
                Group.is_active,
                GroupMember.role,
                GroupMember.joined_at,
            )
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.name)
        )
        groups = []
        for row in res:
            groups.append({
                "group_id": row.group_id,
                "group_name": row.group_name,
                "telegram_group_id": row.telegram_group_id,
                "is_active": row.is_active,
                "role": row.role.value if hasattr(row.role, "value") else str(row.role),
                "joined_at": row.joined_at.isoformat() if row.joined_at else None,
            })
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        user_name = user.full_name if user else str(user_id)
    return web.json_response({"ok": True, "groups": groups, "user_name": user_name})


async def admin_remove_group_member(request):
    """Foydalanuvchini guruhdan chiqarish"""
    _check_admin(request)
    group_id = int(request.match_info["group_id"])
    user_id  = int(request.match_info["user_id"])
    async with get_session() as session:
        gm_res = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        gm = gm_res.scalar_one_or_none()
        if not gm:
            return web.json_response({"error": "A'zo topilmadi"}, status=404)
        await session.delete(gm)

        # Agar guruhning company_id bo'lsa, CompanyMember ham o'chiramiz
        grp_res = await session.execute(select(Group).where(Group.id == group_id))
        grp = grp_res.scalar_one_or_none()
        if grp and grp.company_id:
            cm_res = await session.execute(
                select(CompanyMember).where(
                    CompanyMember.company_id == grp.company_id,
                    CompanyMember.user_id == user_id,
                )
            )
            cm = cm_res.scalar_one_or_none()
            if cm:
                await session.delete(cm)
        await session.commit()
    return web.json_response({"ok": True, "message": "A'zo guruhdan chiqarildi"})


async def admin_tasks(request):
    """Barcha vazifalar (oxirgi 500 ta)"""
    _check_admin(request)
    async with get_session() as session:
        # Workflow step soni (subquery)
        step_count_sq = (
            select(TaskStep.task_id, func.count(TaskStep.id).label("step_count"))
            .group_by(TaskStep.task_id)
            .subquery()
        )
        res = await session.execute(
            select(
                Task.id,
                Task.title,
                Task.status,
                Task.priority,
                Task.deadline,
                Task.created_at,
                Task.company_id,
                User.username.label("creator_username"),
                User.full_name.label("creator_name"),
                Company.name.label("company_name"),
                step_count_sq.c.step_count,
            )
            .join(User, Task.creator_id == User.id)
            .outerjoin(Company, Task.company_id == Company.id)
            .outerjoin(step_count_sq, step_count_sq.c.task_id == Task.id)
            .order_by(Task.created_at.desc())
            .limit(500)
        )
        tasks = []
        for row in res:
            tasks.append({
                "id": row.id,
                "title": row.title,
                "status": row.status.value if hasattr(row.status, 'value') else str(row.status),
                "priority": row.priority.value if hasattr(row.priority, 'value') else str(row.priority),
                "deadline": row.deadline.isoformat() if row.deadline else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "company_name": row.company_name,
                "creator_username": row.creator_username,
                "creator_name": row.creator_name,
                "is_workflow": bool(row.step_count and row.step_count > 0),
                "step_count": int(row.step_count) if row.step_count else 0,
            })
        return web.json_response({"ok": True, "tasks": tasks})


async def admin_task_detail(request):
    """Vazifa to'liq detallari — admin uchun"""
    _check_admin(request)
    task_id = int(request.match_info["task_id"])
    async with get_session() as session:
        res = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.company),
                selectinload(Task.group),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.comments).selectinload(TaskComment.user),
                selectinload(Task.attachments).selectinload(TaskAttachment.user),
                selectinload(Task.steps).selectinload(TaskStep.assignee),
                selectinload(Task.steps).selectinload(TaskStep.comments).selectinload(TaskStepComment.user),
                selectinload(Task.steps).selectinload(TaskStep.attachments).selectinload(TaskStepAttachment.user),
            )
        )
        task = res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )

        def _s(v):
            return v.value if hasattr(v, "value") else (str(v) if v is not None else None)

        def _iso(d):
            return d.isoformat() if d else None

        assignees = []
        for a in (task.assignments or []):
            assignees.append({
                "user_id": a.user_id,
                "name": a.user.full_name if a.user else "—",
                "username": a.user.username if a.user else None,
                "is_responsible": bool(a.is_responsible),
                "status": _s(a.status),
                "started_at": _iso(a.started_at),
                "completed_at": _iso(a.completed_at),
            })

        comments = []
        for cm in sorted(task.comments or [], key=lambda x: x.created_at or datetime.min.replace(tzinfo=_UTC)):
            comments.append({
                "id": cm.id,
                "user_name": cm.user.full_name if cm.user else "—",
                "username": cm.user.username if cm.user else None,
                "text": cm.content,
                "created_at": _iso(cm.created_at),
            })

        attachments = []
        for at in (task.attachments or []):
            attachments.append({
                "id": at.id,
                "user_name": at.user.full_name if at.user else "—",
                "file_name": at.file_name,
                "file_type": at.file_type,
                "file_size": at.file_size,
                "created_at": _iso(at.created_at),
            })

        steps = []
        _proj_adm = _project_step_dates(task.steps or [])
        for st in sorted(task.steps or [], key=lambda x: x.order_index or 0):
            st_comments = [{
                "user_name": c.user.full_name if c.user else "—",
                "text": c.content,
                "created_at": _iso(c.created_at),
            } for c in sorted(st.comments or [], key=lambda x: x.created_at or datetime.min.replace(tzinfo=_UTC))]
            st_atts = [{
                "user_name": a.user.full_name if a.user else "—",
                "file_name": a.file_name,
                "file_url": getattr(a, "file_url", None),
                "created_at": _iso(a.created_at),
            } for a in (st.attachments or [])]
            steps.append({
                "id": st.id,
                "order": st.order_index,
                "title": st.title,
                "status": _s(st.status),
                "assignee_name": st.assignee.full_name if st.assignee else "—",
                "deadline": _iso(st.deadline),
                "duration_days": getattr(st, "duration_days", None),
                "projected_deadline": _iso(_proj_adm.get(st.id)),
                "started_at": _iso(st.started_at),
                "completed_at": _iso(st.completed_at),
                "comments": st_comments,
                "attachments": st_atts,
            })

        data = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": _s(task.status),
            "priority": _s(task.priority),
            "deadline": _iso(task.deadline),
            "created_at": _iso(task.created_at),
            "completed_at": _iso(task.completed_at),
            "creator": {
                "name": task.creator.full_name if task.creator else "—",
                "username": task.creator.username if task.creator else None,
                "telegram_id": task.creator.telegram_id if task.creator else None,
            },
            "company_name": task.company.name if task.company else None,
            "group_name": task.group.name if task.group else None,
            "assignees": assignees,
            "comments": comments,
            "attachments": attachments,
            "steps": steps,
            "is_workflow": bool(steps),
        }
        return web.json_response({"ok": True, "task": data})


async def admin_user_late_tasks(request):
    """Foydalanuvchi kechikib bajargan vazifalar ro'yxati (oxirgi 90 kun)"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    from datetime import timedelta as _td

    async with get_session() as session:
        u = await session.get(User, user_id)
        if not u:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        since = datetime.now(_UTC) - _td(days=90)
        res = await session.execute(
            select(
                Task.id, Task.title, Task.deadline, Task.priority,
                Task.company_id,
                TaskAssignment.completed_at,
            )
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.user_id == user_id,
                TaskAssignment.is_responsible.is_(True),
                TaskAssignment.status == "done",
                TaskAssignment.completed_at.isnot(None),
                Task.deadline.isnot(None),
                TaskAssignment.completed_at > Task.deadline,
                TaskAssignment.completed_at >= since,
            )
            .order_by(TaskAssignment.completed_at.desc())
            .limit(100)
        )
        tasks = []
        for r in res:
            delay_s = (r.completed_at - r.deadline).total_seconds()
            company_name = None
            if r.company_id:
                co = await session.execute(
                    select(Company.name).where(Company.id == r.company_id)
                )
                company_name = co.scalar()
            tasks.append({
                "id":           r.id,
                "title":        r.title,
                "deadline":     r.deadline.isoformat() if r.deadline else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "delay_hours":  round(delay_s / 3600, 1),
                "priority":     r.priority.value if hasattr(r.priority, "value") else str(r.priority),
                "company_name": company_name,
            })

        # Umumiy statistika
        total_done = (await session.execute(
            select(func.count(TaskAssignment.id)).where(
                TaskAssignment.user_id == user_id,
                TaskAssignment.is_responsible.is_(True),
                TaskAssignment.status == "done",
                TaskAssignment.completed_at >= since,
            )
        )).scalar() or 0

        return web.json_response({
            "ok": True,
            "user": {
                "id": u.id,
                "name": u.full_name,
                "username": u.username,
                "telegram_id": u.telegram_id,
            },
            "tasks": tasks,
            "total_late": len(tasks),
            "total_done": total_done,
            "on_time_rate": round((total_done - len(tasks)) / total_done * 100, 1) if total_done else 0,
        })


async def admin_user_overdue_pending(request):
    """Foydalanuvchi HOZIR kechikkan, hali bajarmagan vazifalari (ochiq)."""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        u = await session.get(User, user_id)
        if not u:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        now = datetime.now(_UTC)
        res = await session.execute(
            select(
                Task.id, Task.title, Task.deadline, Task.priority,
                Task.status, Task.company_id,
                TaskAssignment.status.label("asg_status"),
            )
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.user_id == user_id,
                TaskAssignment.is_responsible.is_(True),
                TaskAssignment.status.notin_(["done", "cancelled"]),
                Task.deadline.isnot(None),
                Task.deadline < now,
                Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
            )
            .order_by(Task.deadline.asc())
            .limit(100)
        )
        tasks = []
        for r in res:
            overdue_s = (now - r.deadline).total_seconds()
            company_name = None
            if r.company_id:
                co = await session.execute(
                    select(Company.name).where(Company.id == r.company_id)
                )
                company_name = co.scalar()
            tasks.append({
                "id":           r.id,
                "title":        r.title,
                "deadline":     r.deadline.isoformat() if r.deadline else None,
                "overdue_hours": round(overdue_s / 3600, 1),
                "priority":     r.priority.value if hasattr(r.priority, "value") else str(r.priority),
                "status":       r.asg_status or (r.status.value if hasattr(r.status, "value") else str(r.status)),
                "company_name": company_name,
            })

        return web.json_response({
            "ok": True,
            "user": {"id": u.id, "name": u.full_name, "username": u.username, "telegram_id": u.telegram_id},
            "tasks": tasks,
            "total_overdue": len(tasks),
        })


async def admin_update_task(request):
    """Admin tomonidan vazifa maydonlarini yangilash.
    Qabul qiladi: title, description, status, priority, deadline (ISO format yoki null)."""
    _check_admin(request)
    task_id = int(request.match_info["task_id"])
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "JSON noto'g'ri"}),
            content_type="application/json",
        )

    async with get_session() as session:
        res = await session.execute(select(Task).where(Task.id == task_id))
        task = res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )

        changes = []
        if "title" in body:
            new_title = (body["title"] or "").strip()
            if not new_title or len(new_title) < 2:
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "Sarlavha juda qisqa"}),
                    content_type="application/json",
                )
            if new_title != task.title:
                changes.append(f"sarlavha: '{task.title}' → '{new_title}'")
                task.title = new_title

        if "description" in body:
            new_desc = body["description"] or None
            if new_desc != task.description:
                changes.append("tavsif yangilandi")
                task.description = new_desc

        if "status" in body and body["status"]:
            try:
                new_status = TaskStatus(body["status"])
            except ValueError:
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "Status noto'g'ri"}),
                    content_type="application/json",
                )
            if new_status != task.status:
                changes.append(f"status: {task.status.value} → {new_status.value}")
                task.status = new_status
                if new_status == TaskStatus.DONE and not task.completed_at:
                    task.completed_at = datetime.now(_UTC)
                elif new_status != TaskStatus.DONE and task.completed_at:
                    task.completed_at = None

        if "priority" in body and body["priority"]:
            try:
                new_pri = Priority(body["priority"])
            except ValueError:
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "Muhimlik noto'g'ri"}),
                    content_type="application/json",
                )
            if new_pri != task.priority:
                changes.append(f"muhimlik: {task.priority.value} → {new_pri.value}")
                task.priority = new_pri

        if "deadline" in body:
            raw = body["deadline"]
            if raw in (None, "", "null"):
                if task.deadline is not None:
                    changes.append("deadline olib tashlandi")
                    task.deadline = None
            else:
                try:
                    new_dl = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if new_dl.tzinfo is None:
                        new_dl = new_dl.replace(tzinfo=_UTC)
                except Exception:
                    raise web.HTTPBadRequest(
                        text=json.dumps({"error": "Deadline noto'g'ri (ISO format kerak)"}),
                        content_type="application/json",
                    )
                if new_dl != task.deadline:
                    changes.append(f"deadline: {task.deadline} → {new_dl}")
                    task.deadline = new_dl

        # ── Mas'ulni o'zgartirish (kuzatuvchini mas'ul qilish) ──
        new_responsible_notify = None
        if "responsible_user_id" in body and body["responsible_user_id"]:
            try:
                resp_uid = int(body["responsible_user_id"])
            except (ValueError, TypeError):
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "responsible_user_id noto'g'ri"}),
                    content_type="application/json",
                )
            ares = await session.execute(
                select(TaskAssignment)
                .where(TaskAssignment.task_id == task_id)
                .options(selectinload(TaskAssignment.user))
            )
            assignments = ares.scalars().all()
            target = next((a for a in assignments if a.user_id == resp_uid), None)

            if target is None:
                # Bu user hali tayinlanmagan — yangi mas'ul sifatida qo'shamiz
                u = await session.get(User, resp_uid)
                if not u:
                    raise web.HTTPBadRequest(
                        text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                        content_type="application/json",
                    )
                target = TaskAssignment(
                    task_id=task_id, user_id=resp_uid,
                    is_responsible=True, status="in_progress",
                )
                session.add(target)
                assignments.append(target)
                changes.append(f"yangi mas'ul qo'shildi: {u.full_name}")
                new_responsible_notify = u
            elif not target.is_responsible:
                changes.append(f"mas'ul belgilandi: {target.user.full_name if target.user else resp_uid}")
                new_responsible_notify = target.user

            # Tanlangandan boshqalarni kuzatuvchiga aylantiramiz
            for a in assignments:
                if a.user_id == resp_uid:
                    if not a.is_responsible:
                        a.is_responsible = True
                    if a.status in (None, "",):
                        a.status = "in_progress"
                else:
                    if a.is_responsible:
                        a.is_responsible = False

        if not changes:
            return web.json_response({
                "ok": True, "message": "Hech qanday o'zgarish yo'q",
            })

        await session.commit()
        logger.info(f"Admin: task #{task_id} updated: {'; '.join(changes)}")

        # Yangi mas'ulga xabar
        if new_responsible_notify is not None and getattr(new_responsible_notify, "telegram_id", None):
            bot = request.app.get("bot")
            if bot:
                try:
                    await bot.send_message(
                        new_responsible_notify.telegram_id,
                        f"⭐ <b>Siz mas'ul etib belgilandingiz</b>\n\n"
                        f"📋 Vazifa: <b>{task.title}</b>\n"
                        f"Endi bu vazifa bo'yicha siz mas'ulsiz.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Mas'ul xabari yuborilmadi: {e}")

        return web.json_response({
            "ok": True,
            "message": f"✅ Vazifa yangilandi: {len(changes)} ta o'zgarish",
            "changes": changes,
        })


async def admin_update_step(request):
    """Admin — workflow qadam statusini tahrirlash + keyingi qadamlarni qayta tartiblash."""
    _check_admin(request)
    step_id = int(request.match_info["step_id"])
    body = await request.json()
    new_status = (body.get("status") or "").strip()
    valid = ("pending", "active", "done", "skipped")
    if new_status not in valid:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": f"Status noto'g'ri. Ruxsat: {', '.join(valid)}"}),
            content_type="application/json",
        )

    now = datetime.now(_UTC)
    async with get_session() as session:
        step = await session.get(TaskStep, step_id)
        if not step:
            raise web.HTTPNotFound(text=json.dumps({"error": "Qadam topilmadi"}), content_type="application/json")
        task_id = step.task_id

        # Tanlangan qadam statusini o'rnatamiz
        step.status = new_status
        if new_status == "done":
            step.completed_at = step.completed_at or now
            step.started_at = step.started_at or now
        elif new_status == "active":
            step.started_at = step.started_at or now
            step.completed_at = None
        elif new_status == "pending":
            step.started_at = None
            step.completed_at = None
        elif new_status == "skipped":
            step.completed_at = step.completed_at or now

        # Barcha qadamlarni tartib bilan olib, ketma-ketlikni qayta tiklaymiz
        res = await session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.order_index)
        )
        steps = list(res.scalars().all())

        active_assigned = False
        for s in steps:
            if s.status in ("done", "skipped"):
                continue
            if not active_assigned:
                # Birinchi tugallanmagan qadam — aktiv bo'ladi
                if s.status != "active":
                    _activate_step(s, now)
                active_assigned = True
            else:
                # Aktivdan keyingilar — pending
                if s.status != "pending":
                    s.status = "pending"
                    s.started_at = None
                    s.completed_at = None

        # Vazifa umumiy statusi
        all_done = all(s.status in ("done", "skipped") for s in steps) if steps else False
        task = await session.get(Task, task_id)
        if task:
            if all_done:
                task.status = TaskStatus.DONE
                task.completed_at = task.completed_at or now
            else:
                if task.status == TaskStatus.DONE:
                    task.completed_at = None
                if task.status not in (TaskStatus.CANCELLED,):
                    task.status = TaskStatus.IN_PROGRESS

        await session.commit()
        logger.info(f"Admin: step #{step_id} (task {task_id}) → {new_status}, resequenced")

    return web.json_response({"ok": True, "message": f"✅ Qadam statusi yangilandi: {new_status}"})


async def admin_delete_task(request):
    """Vazifani o'chirish (admin)"""
    _check_admin(request)
    task_id = int(request.match_info["task_id"])
    async with get_session() as session:
        res = await session.execute(select(Task).where(Task.id == task_id))
        task = res.scalar_one_or_none()
        if not task:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Vazifa topilmadi"}),
                content_type="application/json",
            )
        title = task.title
        await session.delete(task)
        await session.commit()
        logger.info(f"Admin: task #{task_id} '{title}' deleted")
        return web.json_response({"ok": True, "message": f"Vazifa #{task_id} o'chirildi"})


# ===================================================================
# =================== HR PANEL API ==================================
# ===================================================================

def _check_hr(request):
    token = request.headers.get("X-HR-Token", "")
    if token != _HR_TOKEN:
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "HR token noto'g'ri"}),
            content_type="application/json",
        )


async def hr_login(request):
    """HR panel login"""
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON xato"}), content_type="application/json")
    username = body.get("username", "")
    password = body.get("password", "")
    if username == _HR_USERNAME and password == _HR_PASSWORD:
        return web.json_response({"ok": True, "token": _HR_TOKEN})
    raise web.HTTPUnauthorized(
        text=json.dumps({"error": "Login yoki parol noto'g'ri"}),
        content_type="application/json",
    )


def _doc_images(doc) -> list:
    """HRDocument dan image paths listini qaytaradi"""
    if doc.images_json:
        try:
            import json as _json
            paths = _json.loads(doc.images_json)
            if isinstance(paths, list):
                return [p for p in paths if p]
        except Exception:
            pass
    if doc.image_path:
        return [doc.image_path]
    return []


async def hr_get_documents(request):
    """HR hujjatlar ro'yxati"""
    _check_hr(request)
    async with get_session() as session:
        res = await session.execute(
            select(HRDocument).order_by(HRDocument.created_at.desc())
        )
        docs = res.scalars().all()
        result = []
        for d in docs:
            asgn_res = await session.execute(
                select(func.count(HRAssignment.id)).where(HRAssignment.document_id == d.id)
            )
            total = asgn_res.scalar() or 0
            conf_res = await session.execute(
                select(func.count(HRAssignment.id)).where(
                    HRAssignment.document_id == d.id,
                    HRAssignment.status == "confirmed"
                )
            )
            confirmed = conf_res.scalar() or 0
            rej_res = await session.execute(
                select(func.count(HRAssignment.id)).where(
                    HRAssignment.document_id == d.id,
                    HRAssignment.status == "rejected"
                )
            )
            rejected = rej_res.scalar() or 0
            images = _doc_images(d)
            result.append({
                "id": d.id,
                "name": d.name,
                "image_path": d.image_path,
                "images": [Path(p).name for p in images],
                "images_count": len(images),
                "has_image": bool(images),
                "has_text": bool(d.extracted_text),
                "text_preview": (d.extracted_text or "")[:100],
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "total": total, "confirmed": confirmed, "rejected": rejected,
                "pending": total - confirmed - rejected,
                "remind_enabled": bool(getattr(d, "remind_enabled", False)),
                "remind_time": getattr(d, "remind_time", None),
                "remind_interval_days": int(getattr(d, "remind_interval_days", 0) or 0),
            })
    return web.json_response({"ok": True, "documents": result})


async def hr_set_reminder(request):
    """Hujjat uchun kunlik eslatma sozlamasini o'rnatish (pending xodimlarга)."""
    _check_hr(request)
    try:
        doc_id = int(request.match_info["document_id"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(text=json.dumps({"error": "Noto'g'ri document_id"}), content_type="application/json")
    body = await request.json()
    enabled = bool(body.get("enabled"))
    rtime = (body.get("time") or "").strip()
    try:
        interval_days = int(body.get("interval_days") or 0)
    except (ValueError, TypeError):
        interval_days = 0
    if interval_days < 0:
        interval_days = 0

    # Vaqt formatini tekshiramiz (HH:MM)
    if enabled:
        import re as _re
        if not _re.match(r"^([01]\d|2[0-3]):[0-5]\d$", rtime):
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "Vaqt HH:MM formatida bo'lsin (masalan 09:00)"}),
                content_type="application/json",
            )

    async with get_session() as session:
        doc = await session.get(HRDocument, doc_id)
        if not doc:
            raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")
        doc.remind_enabled = enabled
        doc.remind_time = rtime if enabled else None
        doc.remind_interval_days = interval_days if enabled else 0
        if not enabled:
            doc.last_reopen_on = None
        await session.commit()
        logger.info(f"HR reminder doc#{doc_id}: enabled={enabled} time={rtime} interval_days={interval_days}")

    return web.json_response({
        "ok": True, "remind_enabled": enabled,
        "remind_time": rtime if enabled else None,
        "remind_interval_days": interval_days if enabled else 0,
    })


async def hr_create_document(request):
    """HR hujjat yaratish — bir nechta rasm yuklash (max 10) + text"""
    _check_hr(request)
    reader = await request.multipart()
    doc_name = ""
    extracted_text = ""
    image_paths = []   # barcha saqlangan rasmlar
    MAX_IMAGES = 10

    async for field in reader:
        if field.name == "name":
            doc_name = (await field.read()).decode("utf-8", errors="replace").strip()
        elif field.name == "text":
            extracted_text = (await field.read()).decode("utf-8", errors="replace").strip()
        elif field.name in ("image", "images") and len(image_paths) < MAX_IMAGES:
            filename = field.filename or "hr_doc.jpg"
            ext = Path(filename).suffix.lower() or ".jpg"
            import uuid as _uuid
            safe_name = f"hr_{_uuid.uuid4().hex[:12]}{ext}"
            save_path = HR_UPLOADS_DIR / safe_name
            with open(save_path, "wb") as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            image_paths.append(str(save_path))

    # OCR — birinchi rasmdan
    if not extracted_text and image_paths:
        try:
            import pytesseract
            from PIL import Image as PILImage
            img = PILImage.open(image_paths[0])
            extracted_text = pytesseract.image_to_string(img, lang="uzb+rus+eng").strip()
        except Exception as e:
            logger.warning(f"OCR xato: {e}")

    if not doc_name:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Hujjat nomi majburiy"}), content_type="application/json")

    images_json_val = json.dumps(image_paths) if image_paths else None

    async with get_session() as session:
        doc = HRDocument(
            name=doc_name,
            image_path=image_paths[0] if image_paths else None,
            images_json=images_json_val,
            extracted_text=extracted_text or None,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

    return web.json_response({
        "ok": True, "id": doc_id, "name": doc_name,
        "extracted_text": extracted_text,
        "images": [Path(p).name for p in image_paths],
    })


async def hr_get_document(request):
    """Bitta hujjat tafsiloti"""
    _check_hr(request)
    doc_id = int(request.match_info["doc_id"])
    async with get_session() as session:
        doc = await session.get(HRDocument, doc_id)
        if not doc:
            raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")
        images = _doc_images(doc)
        return web.json_response({
            "ok": True,
            "id": doc.id, "name": doc.name,
            "image_path": doc.image_path,
            "images": [Path(p).name for p in images],
            "images_count": len(images),
            "extracted_text": doc.extracted_text or "",
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        })


async def hr_update_document(request):
    """Hujjat tahrirlash — nom, matn, va rasm qo'shish/o'chirish"""
    _check_hr(request)
    doc_id = int(request.match_info["doc_id"])

    content_type = request.content_type or ""

    if "multipart" in content_type:
        # Yangi rasm(lar) qo'shish
        reader = await request.multipart()
        MAX_IMAGES = 10
        async with get_session() as session:
            doc = await session.get(HRDocument, doc_id)
            if not doc:
                raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")
            existing = _doc_images(doc)
            new_paths = list(existing)

            async for field in reader:
                if field.name == "name":
                    doc.name = (await field.read()).decode("utf-8", errors="replace").strip()
                elif field.name == "text":
                    doc.extracted_text = (await field.read()).decode("utf-8", errors="replace").strip() or None
                elif field.name in ("image", "images") and len(new_paths) < MAX_IMAGES:
                    filename = field.filename or "hr_doc.jpg"
                    ext = Path(filename).suffix.lower() or ".jpg"
                    import uuid as _uuid
                    safe_name = f"hr_{_uuid.uuid4().hex[:12]}{ext}"
                    save_path = HR_UPLOADS_DIR / safe_name
                    with open(save_path, "wb") as f:
                        while True:
                            chunk = await field.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
                    new_paths.append(str(save_path))

            doc.images_json = json.dumps(new_paths) if new_paths else None
            doc.image_path = new_paths[0] if new_paths else None
            await session.commit()
        return web.json_response({"ok": True, "images": [Path(p).name for p in new_paths]})

    else:
        # JSON patch: name, extracted_text, yoki rasm o'chirish
        body = await request.json()
        async with get_session() as session:
            doc = await session.get(HRDocument, doc_id)
            if not doc:
                raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")
            if "name" in body:
                doc.name = body["name"]
            if "extracted_text" in body:
                doc.extracted_text = body["extracted_text"] or None
            if "delete_image_idx" in body:
                # O'chirilayotgan rasm indeksi
                idx = int(body["delete_image_idx"])
                images = _doc_images(doc)
                if 0 <= idx < len(images):
                    removed = images.pop(idx)
                    try:
                        Path(removed).unlink(missing_ok=True)
                    except Exception:
                        pass
                    doc.images_json = json.dumps(images) if images else None
                    doc.image_path = images[0] if images else None
            await session.commit()
            images = _doc_images(doc)
        return web.json_response({"ok": True, "images": [Path(p).name for p in images]})


async def hr_delete_document(request):
    """Hujjatni o'chirish"""
    _check_hr(request)
    doc_id = int(request.match_info["doc_id"])
    async with get_session() as session:
        doc = await session.get(HRDocument, doc_id)
        if not doc:
            raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")
        # Barcha rasmlarni o'chirish
        for p in _doc_images(doc):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        await session.delete(doc)
        await session.commit()
    return web.json_response({"ok": True})


async def hr_get_users(request):
    """Bot foydalanuvchilari — biriktirish uchun"""
    _check_hr(request)
    async with get_session() as session:
        res = await session.execute(
            select(User).where(User.is_banned == False).order_by(User.full_name)
        )
        users = res.scalars().all()
        return web.json_response({
            "ok": True,
            "users": [
                {
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "full_name": u.full_name,
                    "username": u.username,
                    "is_hr": u.is_hr,
                }
                for u in users
            ]
        })


async def hr_assign_document(request):
    """Hujjatni foydalanuvchilarga biriktirish va bot orqali yuborish"""
    _check_hr(request)
    body = await request.json()
    doc_id = body.get("document_id")
    user_ids = body.get("user_ids", [])
    if not doc_id or not user_ids:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "document_id va user_ids majburiy"}),
            content_type="application/json",
        )

    bot = request.app.get("bot")
    sent = []
    skipped = []

    async with get_session() as session:
        doc = await session.get(HRDocument, doc_id)
        if not doc:
            raise web.HTTPNotFound(text=json.dumps({"error": "Hujjat topilmadi"}), content_type="application/json")

        for uid in user_ids:
            # Allaqachon biriktirilganmi?
            existing = await session.execute(
                select(HRAssignment).where(
                    HRAssignment.document_id == doc_id,
                    HRAssignment.user_id == uid,
                )
            )
            if existing.scalar_one_or_none():
                skipped.append(uid)
                continue

            user = await session.get(User, uid)
            if not user:
                skipped.append(uid)
                continue

            asgn = HRAssignment(document_id=doc_id, user_id=uid, status=HRAssignmentStatus.PENDING)
            session.add(asgn)
            await session.flush()

            # Bot orqali yuborish
            if bot:
                from handlers.hr import send_hr_document
                await send_hr_document(bot, user, asgn, doc)

            sent.append(uid)

        await session.commit()

    return web.json_response({
        "ok": True,
        "sent": len(sent),
        "skipped": len(skipped),
        "message": f"{len(sent)} ta foydalanuvchiga yuborildi",
    })


async def hr_remind_assignment(request):
    """Pending hujjat uchun xodimga bot orqali eslatma yuborish"""
    _check_hr(request)
    try:
        asgn_id = int(request.match_info["assignment_id"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Noto'g'ri assignment_id"}),
            content_type="application/json"
        )

    async with get_session() as session:
        q = (
            select(HRAssignment, User, HRDocument)
            .join(User,       HRAssignment.user_id      == User.id)
            .join(HRDocument, HRAssignment.document_id  == HRDocument.id)
            .where(HRAssignment.id == asgn_id)
        )
        row = (await session.execute(q)).first()
        if not row:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Assignment topilmadi"}),
                content_type="application/json"
            )
        asgn, user, doc = row
        if asgn.status != "pending":
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "Faqat kutilayotgan hujjatlarga eslatma yuboriladi"}),
                content_type="application/json"
            )

    bot = request.app.get("bot")
    if not bot:
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": "Bot mavjud emas"}),
            content_type="application/json"
        )

    try:
        from handlers.hr import hr_doc_keyboard
        text = (
            f"⏰ <b>Eslatma!</b>\n\n"
            f"📄 <b>{doc.name}</b> hujjatini hali ko'rib chiqmadingiz.\n\n"
            f"HR bo'limi sizdan ushbu hujjatni tasdiqlash yoki rad etishingizni kutmoqda.\n\n"
            f"Quyidagi tugmalardan birini bosing ⬇️"
        )
        kb = hr_doc_keyboard(asgn.id)
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as e:
        logger.warning(f"Reminder yuborishda xato (user {user.telegram_id}): {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({"error": f"Xabar yuborib bo'lmadi: {str(e)[:80]}"}),
            content_type="application/json"
        )

    return web.json_response({"ok": True, "sent_to": user.telegram_id})


async def hr_get_assignments(request):
    """Dashboard — barcha biriktirishlar holati"""
    _check_hr(request)
    doc_id = request.rel_url.query.get("doc_id")
    async with get_session() as session:
        q = (
            select(
                HRAssignment.id,
                HRAssignment.status,
                HRAssignment.comment,
                HRAssignment.assigned_at,
                HRAssignment.responded_at,
                User.id.label("user_id"),
                User.full_name,
                User.username,
                User.telegram_id,
                HRDocument.id.label("doc_id"),
                HRDocument.name.label("doc_name"),
            )
            .join(User, HRAssignment.user_id == User.id)
            .join(HRDocument, HRAssignment.document_id == HRDocument.id)
            .order_by(HRAssignment.assigned_at.desc())
        )
        if doc_id:
            q = q.where(HRAssignment.document_id == int(doc_id))
        res = await session.execute(q)
        rows = res.all()

    assignments = []
    for r in rows:
        assignments.append({
            "id": r.id,
            "status": r.status if isinstance(r.status, str) else r.status.value,
            "comment": r.comment,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
            "responded_at": r.responded_at.isoformat() if r.responded_at else None,
            "user_id": r.user_id,
            "full_name": r.full_name,
            "username": r.username,
            "telegram_id": r.telegram_id,
            "doc_id": r.doc_id,
            "doc_name": r.doc_name,
        })
    return web.json_response({"ok": True, "assignments": assignments})


async def hr_stats(request):
    """HR dashboard statistika"""
    _check_hr(request)
    from datetime import timedelta as _td

    async with get_session() as session:
        docs_count = (await session.execute(select(func.count(HRDocument.id)))).scalar() or 0
        total_asgn = (await session.execute(select(func.count(HRAssignment.id)))).scalar() or 0
        confirmed  = (await session.execute(
            select(func.count(HRAssignment.id)).where(HRAssignment.status == "confirmed")
        )).scalar() or 0
        rejected   = (await session.execute(
            select(func.count(HRAssignment.id)).where(HRAssignment.status == "rejected")
        )).scalar() or 0
        pending    = total_asgn - confirmed - rejected
        confirmation_rate = round(confirmed / total_asgn * 100, 1) if total_asgn else 0

        # ===== Bugungi faollik =====
        now_tz = datetime.now(_TZ)
        today_local = now_tz.date()
        today_start = datetime.combine(today_local, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
        today_end = today_start + _td(days=1)

        today_docs = (await session.execute(
            select(func.count(HRDocument.id)).where(
                HRDocument.created_at >= today_start, HRDocument.created_at < today_end
            )
        )).scalar() or 0
        today_assigned = (await session.execute(
            select(func.count(HRAssignment.id)).where(
                HRAssignment.assigned_at >= today_start, HRAssignment.assigned_at < today_end
            )
        )).scalar() or 0
        today_responded = (await session.execute(
            select(func.count(HRAssignment.id)).where(
                HRAssignment.responded_at >= today_start, HRAssignment.responded_at < today_end
            )
        )).scalar() or 0
        today_confirmed = (await session.execute(
            select(func.count(HRAssignment.id)).where(
                HRAssignment.responded_at >= today_start, HRAssignment.responded_at < today_end,
                HRAssignment.status == "confirmed",
            )
        )).scalar() or 0

        # ===== O'rtacha javob vaqti (soatda) =====
        avg_res = await session.execute(
            select(
                func.avg(
                    func.extract("epoch", HRAssignment.responded_at)
                    - func.extract("epoch", HRAssignment.assigned_at)
                )
            ).where(
                HRAssignment.responded_at.isnot(None),
                HRAssignment.assigned_at.isnot(None),
            )
        )
        avg_seconds = avg_res.scalar()
        avg_response_hours = round(float(avg_seconds or 0) / 3600, 1) if avg_seconds else 0

        # ===== 30 kunlik trend =====
        activity_30d = []
        for d in range(29, -1, -1):
            day = now_tz.date() - _td(days=d)
            ds = datetime.combine(day, datetime.min.time(), tzinfo=_TZ).astimezone(_UTC)
            de = ds + _td(days=1)
            asg = (await session.execute(
                select(func.count(HRAssignment.id)).where(
                    HRAssignment.assigned_at >= ds, HRAssignment.assigned_at < de
                )
            )).scalar() or 0
            cnf = (await session.execute(
                select(func.count(HRAssignment.id)).where(
                    HRAssignment.responded_at >= ds, HRAssignment.responded_at < de,
                    HRAssignment.status == "confirmed",
                )
            )).scalar() or 0
            rej = (await session.execute(
                select(func.count(HRAssignment.id)).where(
                    HRAssignment.responded_at >= ds, HRAssignment.responded_at < de,
                    HRAssignment.status == "rejected",
                )
            )).scalar() or 0
            activity_30d.append({
                "date": day.strftime("%d.%m"),
                "assigned": asg,
                "confirmed": cnf,
                "rejected": rej,
            })

        # ===== Hafta kunlari (90 kun) =====
        weekday_assigned = [0] * 7
        weekday_responded = [0] * 7
        since_90 = datetime.now(_UTC) - _td(days=90)
        wa_res = await session.execute(
            select(
                func.extract("dow", HRAssignment.assigned_at).label("dow"),
                func.count(HRAssignment.id),
            )
            .where(HRAssignment.assigned_at >= since_90)
            .group_by(func.extract("dow", HRAssignment.assigned_at))
        )
        for r in wa_res.all():
            pg = int(r.dow); idx = (pg + 6) % 7
            weekday_assigned[idx] = int(r[1])
        wr_res = await session.execute(
            select(
                func.extract("dow", HRAssignment.responded_at).label("dow"),
                func.count(HRAssignment.id),
            )
            .where(HRAssignment.responded_at >= since_90)
            .group_by(func.extract("dow", HRAssignment.responded_at))
        )
        for r in wr_res.all():
            pg = int(r.dow); idx = (pg + 6) % 7
            weekday_responded[idx] = int(r[1])

        # ===== Eng faol xodimlar (eng ko'p tasdiqlagan, 30 kun) =====
        since_30 = datetime.now(_UTC) - _td(days=30)
        tu_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(HRAssignment.id).label("c"),
            )
            .join(HRAssignment, HRAssignment.user_id == User.id)
            .where(
                HRAssignment.status == "confirmed",
                HRAssignment.responded_at >= since_30,
            )
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(HRAssignment.id).desc())
            .limit(8)
        )
        top_responders = [
            {"name": r.full_name, "username": r.username, "count": r.c}
            for r in tu_res.all()
        ]

        # ===== Eng ko'p tarqalgan hujjatlar =====
        td_res = await session.execute(
            select(
                HRDocument.id, HRDocument.name,
                func.count(HRAssignment.id).label("c"),
            )
            .join(HRAssignment, HRAssignment.document_id == HRDocument.id)
            .group_by(HRDocument.id, HRDocument.name)
            .order_by(func.count(HRAssignment.id).desc())
            .limit(6)
        )
        top_docs = [
            {"name": r.name, "count": r.c}
            for r in td_res.all()
        ]

        # ===== Javob bermayotgan xodimlar (>3 kun) =====
        three_days_ago = datetime.now(_UTC) - _td(days=3)
        slow_res = await session.execute(
            select(
                User.id, User.full_name, User.username,
                func.count(HRAssignment.id).label("c"),
            )
            .join(HRAssignment, HRAssignment.user_id == User.id)
            .where(
                HRAssignment.status == "pending",
                HRAssignment.assigned_at < three_days_ago,
            )
            .group_by(User.id, User.full_name, User.username)
            .order_by(func.count(HRAssignment.id).desc())
            .limit(8)
        )
        slow_responders = [
            {"name": r.full_name, "username": r.username, "count": r.c}
            for r in slow_res.all()
        ]

    return web.json_response({
        "ok": True,
        "documents": docs_count,
        "total": total_asgn,
        "confirmed": confirmed,
        "rejected": rejected,
        "pending": pending,
        "confirmation_rate": confirmation_rate,
        "avg_response_hours": avg_response_hours,
        "today": {
            "docs": today_docs,
            "assigned": today_assigned,
            "responded": today_responded,
            "confirmed": today_confirmed,
        },
        "activity_30d": activity_30d,
        "weekday_activity": {
            "labels": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"],
            "assigned": weekday_assigned,
            "responded": weekday_responded,
        },
        "top_responders": top_responders,
        "top_docs": top_docs,
        "slow_responders": slow_responders,
    })


# ===== HR image serve =====
async def hr_serve_image(request):
    """HR hujjat rasmini serving"""
    filename = request.match_info["filename"]
    # Security: no path traversal
    if ".." in filename or "/" in filename:
        raise web.HTTPForbidden()
    path = HR_UPLOADS_DIR / filename
    if not path.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


# ===== Employee portal API =====
async def employee_my_docs(request):
    """Xodimning o'z HR hujjatlari — Telegram initData orqali auth"""
    # auth_middleware /employee/api ni skip qiladi — shuning uchun bu yerda o'zimiz parse qilamiz
    tg_id = request.get("user_telegram_id")  # agar middleware o'tkazgan bo'lsa
    if not tg_id:
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        if init_data:
            user_info = validate_init_data(init_data)
            if user_info:
                tg_id = user_info.get("telegram_id")
        # Fallback: token auth (Telegram Desktop)
        if not tg_id:
            auth_token = request.headers.get("X-Auth-Token", "")
            if auth_token:
                user_info = validate_auth_token(auth_token)
                if user_info:
                    tg_id = user_info.get("telegram_id")
    if not tg_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "Telegram orqali kirish kerak"}),
            content_type="application/json"
        )
    async with get_session() as session:
        # User topish
        user_res = await session.execute(
            select(User).where(User.telegram_id == tg_id)
        )
        user = user_res.scalar_one_or_none()
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json"
            )

        # Assignments
        q = (
            select(
                HRAssignment.id,
                HRAssignment.status,
                HRAssignment.comment,
                HRAssignment.assigned_at,
                HRAssignment.responded_at,
                HRDocument.id.label("doc_id"),
                HRDocument.name.label("doc_name"),
                HRDocument.images_json,
                HRDocument.image_path,
                HRDocument.extracted_text,
            )
            .join(HRDocument, HRAssignment.document_id == HRDocument.id)
            .where(HRAssignment.user_id == user.id)
            .order_by(HRAssignment.assigned_at.desc())
        )
        res = await session.execute(q)
        rows = res.fetchall()

        # Stats
        total     = len(rows)
        confirmed = sum(1 for r in rows if r.status == "confirmed")
        rejected  = sum(1 for r in rows if r.status == "rejected")
        pending   = sum(1 for r in rows if r.status == "pending")

        assignments = []
        for r in rows:
            # first image
            first_img = None
            if r.images_json:
                try:
                    imgs = json.loads(r.images_json)
                    if imgs:
                        first_img = Path(imgs[0]).name
                except Exception:
                    pass
            if not first_img and r.image_path:
                first_img = Path(r.image_path).name

            assignments.append({
                "id":           r.id,
                "doc_id":       r.doc_id,
                "doc_name":     r.doc_name,
                "doc_image":    first_img,
                "doc_text_preview": (r.extracted_text or "")[:120],
                "status":       r.status,
                "comment":      r.comment,
                "assigned_at":  r.assigned_at.isoformat() if r.assigned_at else None,
                "responded_at": r.responded_at.isoformat() if r.responded_at else None,
            })

    return web.json_response({
        "ok": True,
        "user": {
            "id":        user.id,
            "full_name": user.full_name,
            "username":  user.username,
            "telegram_id": user.telegram_id,
        },
        "stats": {
            "total": total, "confirmed": confirmed,
            "rejected": rejected, "pending": pending
        },
        "assignments": assignments,
    })


async def employee_respond(request):
    """Xodim hujjat assignmentga tasdiqlash yoki rad etish javobi"""
    assignment_id_str = request.match_info.get("assignment_id", "")
    try:
        assignment_id = int(assignment_id_str)
    except ValueError:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Noto'g'ri assignment_id"}),
            content_type="application/json"
        )

    # Auth (same pattern as employee_my_docs)
    tg_id = request.get("user_telegram_id")
    if not tg_id:
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        if init_data:
            user_info = validate_init_data(init_data)
            if user_info:
                tg_id = user_info.get("telegram_id")
        if not tg_id:
            auth_token = request.headers.get("X-Auth-Token", "")
            if auth_token:
                user_info = validate_auth_token(auth_token)
                if user_info:
                    tg_id = user_info.get("telegram_id")
    if not tg_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "Telegram orqali kirish kerak"}),
            content_type="application/json"
        )

    body = await request.json()
    action  = body.get("action", "")
    comment = (body.get("comment") or "").strip()

    if action not in ("confirmed", "rejected"):
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "action: 'confirmed' yoki 'rejected' bo'lishi kerak"}),
            content_type="application/json"
        )
    if action == "rejected" and not comment:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Rad etish sababini yozing"}),
            content_type="application/json"
        )

    async with get_session() as session:
        user_res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json"
            )

        asgn_res = await session.execute(
            select(HRAssignment).where(
                HRAssignment.id == assignment_id,
                HRAssignment.user_id == user.id
            )
        )
        asgn = asgn_res.scalar_one_or_none()
        if not asgn:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Assignment topilmadi"}),
                content_type="application/json"
            )
        if asgn.status != "pending":
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "Bu hujjatga allaqachon javob berilgan"}),
                content_type="application/json"
            )

        asgn.status      = action
        asgn.comment     = comment if action == "rejected" else None
        asgn.responded_at = datetime.now(_TZ)
        await session.commit()

    return web.json_response({"ok": True, "status": action})


async def serve_employee(request):
    p = WEBAPP_DIR / "employee.html"
    if p.exists():
        return web.FileResponse(p, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache", "Expires": "0",
        })
    raise web.HTTPNotFound()


# ===== Serve HR panel =====
async def serve_hr(request):
    hr_html = WEBAPP_DIR / "hr.html"
    if hr_html.exists():
        return web.FileResponse(hr_html)
    raise web.HTTPNotFound()


async def admin_toggle_hr(request):
    """Foydalanuvchiga HR huquqi berish/olish"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        user.is_hr = not user.is_hr
        await session.commit()
        return web.json_response({"ok": True, "is_hr": user.is_hr, "full_name": user.full_name})


async def admin_toggle_feedback_admin(request):
    """Foydalanuvchiga Murojaat admini huquqi berish/olish"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        user.is_feedback_admin = not bool(user.is_feedback_admin)
        await session.commit()
        new_val = user.is_feedback_admin
        tg_id = user.telegram_id
        full_name = user.full_name

    # Yangi murojaat adminini xabardor qilamiz
    bot = request.app.get("bot")
    if bot and new_val and tg_id:
        try:
            await bot.send_message(
                tg_id,
                "📨 Sizga <b>Murojaat admini</b> huquqi berildi.\n\n"
                "Endi foydalanuvchilarning taklif va shikoyatlari sizga keladi va siz javob bera olasiz.",
            )
        except Exception:
            pass

    return web.json_response({"ok": True, "is_feedback_admin": new_val, "full_name": full_name})


async def admin_toggle_ai(request):
    """Foydalanuvchiga AI maslahatchini yoqish/o'chirish"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        user.ai_enabled = not bool(getattr(user, "ai_enabled", False))
        await session.commit()
        new_val = user.ai_enabled
        tg_id = user.telegram_id
        full_name = user.full_name

    bot = request.app.get("bot")
    if bot and tg_id:
        try:
            if new_val:
                await bot.send_message(
                    tg_id,
                    "🤖 <b>AI Yordamchi yoqildi!</b>\n\n"
                    "Endi mini ilovadagi <b>AI</b> bo'limida men bilan suhbatlashishingiz mumkin.\n\n"
                    "Men sizga:\n"
                    "• 💡 Vazifalaringiz bo'yicha maslahat beraman\n"
                    "• 📊 Nimadan boshlashni aytaman\n"
                    "• ⏰ «Buni ertaga 15:00 da eslat» desangiz — eslatib turaman\n"
                    "• 💪 Ruhlantiraman!\n\n"
                    "Sinab ko'ring 😊",
                )
            else:
                await bot.send_message(tg_id, "🤖 AI Yordamchi o'chirildi.")
        except Exception:
            pass

    return web.json_response({"ok": True, "ai_enabled": new_val, "full_name": full_name})


# ===================================================================
async def admin_toggle_ban(request):
    """Foydalanuvchini ban/unban qilish"""
    _check_admin(request)
    user_id = int(request.match_info["user_id"])
    async with get_session() as session:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()
        if not user:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "Foydalanuvchi topilmadi"}),
                content_type="application/json",
            )
        user.is_banned = not user.is_banned
        await session.commit()
        action = "bloklandi" if user.is_banned else "blokdan chiqarildi"
        logger.info(f"Admin: user {user.telegram_id} ({user.full_name}) {action}")
        return web.json_response({
            "ok": True,
            "is_banned": user.is_banned,
            "message": f"{user.full_name} {action}",
        })


# ═══════════════════════════════════════════════════════════════
#  MUROJAAT (taklif / shikoyat) API
# ═══════════════════════════════════════════════════════════════

_FB_TYPE_LABEL = {"complaint": "Shikoyat", "suggestion": "Taklif"}
_FB_STATUS_LABEL = {
    "pending": "Ko'rib chiqilmoqda",
    "in_review": "Ko'rib chiqilmoqda",
    "resolved": "Yechim berildi",
}


def _fb_is_admin(user) -> bool:
    """Foydalanuvchi murojaat admini yoki super-adminmi?"""
    if user.telegram_id in (settings.admin_ids_list or []):
        return True
    return bool(getattr(user, "is_feedback_admin", False))


def _feedback_to_dict(fb, *, for_admin: bool = False) -> dict:
    atts = []
    for a in (fb.attachments or []):
        atts.append({
            "file_url": a.file_url,
            "file_type": a.file_type,
            "file_name": a.file_name,
            "has_tg_file": bool(a.file_id and not a.file_url),
        })
    replies = []
    for r in (fb.replies or []):
        rname = getattr(r, "admin_name", None) or (r.admin.full_name if r.admin else "Admin")
        replies.append({
            "content": r.content,
            "admin_name": rname,
            "created_at": r.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if r.created_at else "",
        })
    d = {
        "id": fb.id,
        "type": fb.type,
        "type_label": _FB_TYPE_LABEL.get(fb.type, fb.type),
        "is_anonymous": bool(fb.is_anonymous),
        "content": fb.content,
        "status": fb.status,
        "status_label": _FB_STATUS_LABEL.get(fb.status, fb.status),
        "created_at": fb.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if fb.created_at else "",
        "attachments": atts,
        "replies": replies,
    }
    # Muhokamaga yo'naltirishlar (HR panel uchun)
    discussions = []
    _DISC_LABEL = {"pending": "🕓 Kutilmoqda", "answered": "✅ Javob berdi", "rejected": "❌ Rad etdi"}
    for dsc in (getattr(fb, "discussions", None) or []):
        tu = dsc.target_user
        discussions.append({
            "id": dsc.id,
            "target_name": (tu.full_name if tu else "Noma'lum"),
            "target_username": (tu.username if tu else None),
            "hr_comment": dsc.hr_comment,
            "status": dsc.status,
            "status_label": _DISC_LABEL.get(dsc.status, dsc.status),
            "response": dsc.response,
            "created_at": dsc.created_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if dsc.created_at else "",
            "responded_at": dsc.responded_at.astimezone(_TZ).strftime("%d.%m.%Y %H:%M") if dsc.responded_at else "",
        })
    d["discussions"] = discussions

    if for_admin:
        if fb.is_anonymous:
            d["from_name"] = "🕵️ Anonim foydalanuvchi"
        else:
            u = fb.user
            d["from_name"] = (f"@{u.username}" if u and u.username else (u.full_name if u else "Noma'lum"))
    return d


async def api_feedback_meta(request):
    """Joriy foydalanuvchi murojaat adminimi?"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    return web.json_response({"is_admin": _fb_is_admin(user)})


async def api_feedback_upload(request):
    """Murojaat uchun mediya yuklash (multipart) → {file_url, file_type, file_name}"""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        raise web.HTTPBadRequest(text=json.dumps({"error": "Fayl yo'q"}))

    filename = field.filename or "file"
    safe_name = f"fb_{user.id}_{int(datetime.now(_UTC).timestamp())}_{filename.replace('/', '_')[:120]}"
    file_path = ATTACH_DIR / safe_name
    MAX_SIZE = 100 * 1024 * 1024
    size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await field.read_chunk(size=65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SIZE:
                f.close()
                file_path.unlink(missing_ok=True)
                raise web.HTTPBadRequest(text=json.dumps({"error": "Fayl 100 MB dan katta"}))
            f.write(chunk)

    mime = field.headers.get("Content-Type", "application/octet-stream")
    if mime.startswith("image/"):
        ftype = "photo"
    elif mime.startswith("video/"):
        ftype = "video"
    elif mime.startswith("audio/"):
        ftype = "voice"
    else:
        ftype = "document"

    return web.json_response({
        "file_url": f"/uploads/{safe_name}",
        "file_type": ftype,
        "file_name": filename,
    })


async def api_feedback_create(request):
    """Yangi murojaat yaratish (JSON) + adminlarga yuborish."""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))

    ftype = body.get("type")
    if ftype not in ("complaint", "suggestion"):
        raise web.HTTPBadRequest(text=json.dumps({"error": "Noto'g'ri tur"}))
    content = (body.get("content") or "").strip()
    if len(content) < 3:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Matn juda qisqa"}))
    content = content[:4000]
    is_anon = bool(body.get("is_anonymous"))
    attachments = body.get("attachments") or []

    async with get_session() as session:
        fb = Feedback(
            user_id=user.id, type=ftype, is_anonymous=is_anon,
            content=content, status=FeedbackStatus.PENDING.value,
        )
        session.add(fb)
        await session.flush()
        for a in attachments[:10]:
            if not isinstance(a, dict):
                continue
            session.add(FeedbackAttachment(
                feedback_id=fb.id,
                file_url=a.get("file_url"),
                file_type=a.get("file_type", "document"),
                file_name=a.get("file_name"),
            ))
        await session.commit()
        fb_id = fb.id

        res = await session.execute(
            select(Feedback).where(Feedback.id == fb_id)
            .options(selectinload(Feedback.attachments), selectinload(Feedback.user))
        )
        fb_full = res.scalar_one()

        bot = request.app.get("bot")
        if bot:
            try:
                from handlers.feedback import notify_feedback_admins
                await notify_feedback_admins(bot, session, fb_full)
            except Exception as e:
                logger.warning(f"Feedback notify admins xatosi: {e}")

    return web.json_response({"ok": True, "id": fb_id, "status": "pending"}, status=201)


async def api_feedback_my(request):
    """Mening murojaatlarim — holat va javoblar bilan."""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))

    async with get_session() as session:
        res = await session.execute(
            select(Feedback).where(Feedback.user_id == user.id)
            .options(
                selectinload(Feedback.attachments),
                selectinload(Feedback.replies).selectinload(FeedbackReply.admin),
            )
            .order_by(Feedback.created_at.desc())
        )
        items = [_feedback_to_dict(fb) for fb in res.scalars().all()]
    return web.json_response({"items": items})


async def api_feedback_inbox(request):
    """Murojaat adminlari uchun — barcha murojaatlar."""
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    if not _fb_is_admin(user):
        return web.json_response({"error": "forbidden"}, status=403)

    status_filter = request.query.get("status")  # pending | resolved | None
    async with get_session() as session:
        stmt = select(Feedback).options(
            selectinload(Feedback.attachments),
            selectinload(Feedback.user),
            selectinload(Feedback.replies).selectinload(FeedbackReply.admin),
        ).order_by(Feedback.created_at.desc())
        if status_filter == "pending":
            stmt = stmt.where(Feedback.status != FeedbackStatus.RESOLVED.value)
        elif status_filter == "resolved":
            stmt = stmt.where(Feedback.status == FeedbackStatus.RESOLVED.value)
        res = await session.execute(stmt)
        items = [_feedback_to_dict(fb, for_admin=True) for fb in res.scalars().all()]
    return web.json_response({"items": items})


async def api_feedback_reply(request):
    """Admin javobi → murojaat egasiga yuboriladi."""
    fb_id = int(request.match_info["feedback_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    if not _fb_is_admin(user):
        return web.json_response({"error": "forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}))
    reply_text = (body.get("content") or "").strip()
    if len(reply_text) < 2:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Javob juda qisqa"}))
    reply_text = reply_text[:4000]

    async with get_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            return web.json_response({"error": "not found"}, status=404)
        session.add(FeedbackReply(
            feedback_id=fb_id, admin_id=user.id,
            admin_name=user.full_name, source="admin", content=reply_text,
        ))
        fb.status = FeedbackStatus.RESOLVED.value
        fb.resolved_at = datetime.now(_TZ)
        submitter = await session.get(User, fb.user_id)
        fb_type = fb.type
        submitter_tg = submitter.telegram_id if submitter else None
        await session.commit()

    bot = request.app.get("bot")
    if bot and submitter_tg:
        try:
            await bot.send_message(
                submitter_tg,
                f"📬 <b>Murojaatingizga javob keldi</b>  <code>#{fb_id}</code>\n\n"
                f"{_FB_TYPE_LABEL.get(fb_type, fb_type)}\n\n"
                f"✍️ <b>Javob:</b>\n{reply_text}\n\n"
                f"👤 Javob bergan: {user.full_name}\n"
                f"📊 Holat: ✅ Yechim berildi",
            )
        except Exception as e:
            logger.warning(f"Feedback reply notify xatosi: {e}")

    return web.json_response({"ok": True, "status": "resolved"})


async def api_feedback_resolve(request):
    """Admin murojaatni yechilgan deb belgilaydi (matnsiz)."""
    fb_id = int(request.match_info["feedback_id"])
    user = await get_user_from_request(request)
    if not user:
        raise web.HTTPNotFound(text=json.dumps({"error": "Foydalanuvchi topilmadi"}))
    if not _fb_is_admin(user):
        return web.json_response({"error": "forbidden"}, status=403)

    async with get_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            return web.json_response({"error": "not found"}, status=404)
        fb.status = FeedbackStatus.RESOLVED.value
        fb.resolved_at = datetime.now(_TZ)
        submitter = await session.get(User, fb.user_id)
        fb_type = fb.type
        submitter_tg = submitter.telegram_id if submitter else None
        await session.commit()

    bot = request.app.get("bot")
    if bot and submitter_tg:
        try:
            await bot.send_message(
                submitter_tg,
                f"📬 <b>Murojaatingiz ko'rib chiqildi</b>  <code>#{fb_id}</code>\n\n"
                f"{_FB_TYPE_LABEL.get(fb_type, fb_type)}\n"
                f"📊 Holat: ✅ Yechim berildi\n\n"
                f"👤 {user.full_name} murojaatingizni yechilgan deb belgiladi.",
            )
        except Exception as e:
            logger.warning(f"Feedback resolve notify xatosi: {e}")

    return web.json_response({"ok": True, "status": "resolved"})


# ───── HR panel uchun murojaat (taklif/shikoyat) ─────

async def hr_feedback_list(request):
    """HR panel — turi bo'yicha murojaatlar (suggestion | complaint)."""
    _check_hr(request)
    ftype = request.query.get("type")
    status_filter = request.query.get("status")
    async with get_session() as session:
        stmt = select(Feedback).options(
            selectinload(Feedback.attachments),
            selectinload(Feedback.user),
            selectinload(Feedback.replies).selectinload(FeedbackReply.admin),
            selectinload(Feedback.discussions).selectinload(FeedbackDiscussion.target_user),
        ).order_by(Feedback.created_at.desc())
        if ftype in ("suggestion", "complaint"):
            stmt = stmt.where(Feedback.type == ftype)
        if status_filter == "pending":
            stmt = stmt.where(Feedback.status != FeedbackStatus.RESOLVED.value)
        elif status_filter == "resolved":
            stmt = stmt.where(Feedback.status == FeedbackStatus.RESOLVED.value)
        res = await session.execute(stmt)
        rows = list(res.scalars().all())
        items = [_feedback_to_dict(fb, for_admin=True) for fb in rows]
        pending = sum(1 for fb in rows if fb.status != FeedbackStatus.RESOLVED.value)
    return web.json_response({"items": items, "pending": pending})


async def hr_feedback_discuss(request):
    """HR murojaatni bir yoki bir nechta userga muhokamaga yo'naltiradi (izoh bilan)."""
    _check_hr(request)
    fb_id = int(request.match_info["feedback_id"])
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}), content_type="application/json")
    user_ids = body.get("user_ids") or []
    hr_comment = (body.get("comment") or "").strip()[:2000]
    if not user_ids:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Kamida bitta odam tanlang"}), content_type="application/json")

    bot = request.app.get("bot")
    sent = 0
    async with get_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            return web.json_response({"error": "not found"}, status=404)

        # Atatchmentlarni muhokama uchun olamiz
        att_res = await session.execute(
            select(FeedbackAttachment).where(FeedbackAttachment.feedback_id == fb_id)
        )
        atts = list(att_res.scalars().all())
        ftype = fb.type
        fb_content = fb.content

        for uid in user_ids:
            try:
                uid = int(uid)
            except (ValueError, TypeError):
                continue
            target = await session.get(User, uid)
            if not target:
                continue
            disc = FeedbackDiscussion(
                feedback_id=fb_id, target_user_id=uid,
                hr_comment=hr_comment or None, status="pending",
            )
            session.add(disc)
            await session.flush()
            disc_id = disc.id

            # Botdan o'sha userga yuboramiz
            if bot and target.telegram_id:
                type_label = _FB_TYPE_LABEL.get(ftype, ftype)
                msg = (
                    f"🗣 <b>Muhokama uchun yo'naltirildi</b>\n\n"
                    f"📌 {type_label}\n"
                    f"📝 {fb_content or '—'}\n"
                )
                if hr_comment:
                    msg += f"\n💬 <b>HR izohi:</b>\n{hr_comment}\n"
                msg += "\nQuyidagidan birini tanlang:"
                kb = {
                    "inline_keyboard": [[
                        {"text": "✅ Javob berish", "callback_data": f"fbd_answer:{disc_id}"},
                        {"text": "❌ Rad etish", "callback_data": f"fbd_reject:{disc_id}"},
                    ]]
                }
                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kbm = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="✅ Javob berish", callback_data=f"fbd_answer:{disc_id}"),
                        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"fbd_reject:{disc_id}"),
                    ]])
                    await bot.send_message(target.telegram_id, msg, reply_markup=kbm)
                    # Media'ni ham yuboramiz
                    if atts:
                        try:
                            from handlers.feedback import _send_attachments
                            await _send_attachments(bot, target.telegram_id, atts)
                        except Exception:
                            pass
                    sent += 1
                except Exception as e:
                    logger.warning(f"Muhokama yuborib bo'lmadi uid={uid}: {e}")
        await session.commit()

    return web.json_response({"ok": True, "sent": sent})


async def hr_feedback_reply(request):
    """HR javobi → murojaat egasiga yuboriladi (HR bo'limi nomidan)."""
    _check_hr(request)
    fb_id = int(request.match_info["feedback_id"])
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text=json.dumps({"error": "JSON noto'g'ri"}), content_type="application/json")
    reply_text = (body.get("content") or "").strip()
    if len(reply_text) < 2:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Javob juda qisqa"}), content_type="application/json")
    reply_text = reply_text[:4000]

    async with get_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            return web.json_response({"error": "not found"}, status=404)
        session.add(FeedbackReply(
            feedback_id=fb_id, admin_id=None,
            admin_name="HR bo'limi", source="hr", content=reply_text,
        ))
        fb.status = FeedbackStatus.RESOLVED.value
        fb.resolved_at = datetime.now(_TZ)
        submitter = await session.get(User, fb.user_id)
        fb_type = fb.type
        submitter_tg = submitter.telegram_id if submitter else None
        await session.commit()

    bot = request.app.get("bot")
    if bot and submitter_tg:
        try:
            await bot.send_message(
                submitter_tg,
                f"📬 <b>Murojaatingizga javob keldi</b>  <code>#{fb_id}</code>\n\n"
                f"{_FB_TYPE_LABEL.get(fb_type, fb_type)}\n\n"
                f"✍️ <b>Javob:</b>\n{reply_text}\n\n"
                f"👤 Javob bergan: HR bo'limi\n"
                f"📊 Holat: ✅ Yechim berildi",
            )
        except Exception as e:
            logger.warning(f"HR feedback reply notify xatosi: {e}")

    return web.json_response({"ok": True, "status": "resolved"})


async def hr_feedback_resolve(request):
    """HR murojaatni yechilgan deb belgilaydi."""
    _check_hr(request)
    fb_id = int(request.match_info["feedback_id"])
    async with get_session() as session:
        fb = await session.get(Feedback, fb_id)
        if not fb:
            return web.json_response({"error": "not found"}, status=404)
        fb.status = FeedbackStatus.RESOLVED.value
        fb.resolved_at = datetime.now(_TZ)
        submitter = await session.get(User, fb.user_id)
        fb_type = fb.type
        submitter_tg = submitter.telegram_id if submitter else None
        await session.commit()

    bot = request.app.get("bot")
    if bot and submitter_tg:
        try:
            await bot.send_message(
                submitter_tg,
                f"📬 <b>Murojaatingiz ko'rib chiqildi</b>  <code>#{fb_id}</code>\n\n"
                f"{_FB_TYPE_LABEL.get(fb_type, fb_type)}\n"
                f"📊 Holat: ✅ Yechim berildi\n\n"
                f"👤 HR bo'limi murojaatingizni yechilgan deb belgiladi.",
            )
        except Exception as e:
            logger.warning(f"HR feedback resolve notify xatosi: {e}")

    return web.json_response({"ok": True, "status": "resolved"})


# ===== App Factory =====

def create_api_app(bot=None) -> web.Application:
    """API ilovasini yaratish"""
    app = web.Application(middlewares=[cors_middleware, auth_middleware])
    if bot is not None:
        app["bot"] = bot

    # API routes
    app.router.add_get("/api/workspaces", api_get_workspaces)
    app.router.add_delete("/api/companies/{company_id}/leave", api_leave_company)
    app.router.add_delete("/api/companies/{company_id}", api_delete_company)
    app.router.add_get("/api/invite-link", api_get_invite_link)
    app.router.add_get("/api/companies/{company_id}/members", api_get_company_members)
    app.router.add_get("/api/companies/{company_id}/info", api_get_company_info)
    app.router.add_delete("/api/companies/{company_id}/members/{user_id}", api_remove_company_member)
    app.router.add_put("/api/companies/{company_id}/members/{user_id}", api_update_member)
    app.router.add_post("/api/companies/{company_id}/reassign", api_reassign_tasks)
    app.router.add_get("/api/i18n", api_get_i18n)
    app.router.add_post("/api/i18n/set-lang", api_set_language)
    app.router.add_get("/api/tasks", api_get_tasks)
    app.router.add_get("/api/tasks/{task_id}/tree", api_get_task_tree)
    app.router.add_get("/api/tasks/{task_id}", api_get_task)
    app.router.add_get("/api/tasks/{task_id}/chart", api_get_task_chart)
    app.router.add_post("/api/tasks", api_create_task)
    app.router.add_post("/api/tasks/create-workflow", api_create_workflow)
    app.router.add_patch("/api/tasks/{task_id}/status", api_update_status)
    app.router.add_patch("/api/tasks/{task_id}/my-status", api_update_my_status)
    app.router.add_patch("/api/tasks/{task_id}/priority", api_update_priority)
    app.router.add_patch("/api/tasks/{task_id}/edit", api_edit_task)
    app.router.add_post("/api/tasks/{task_id}/start", api_task_start)
    app.router.add_post("/api/tasks/{task_id}/complete", api_task_complete)
    app.router.add_delete("/api/tasks/{task_id}", api_task_delete)
    app.router.add_post("/api/tasks/{task_id}/attachments", api_upload_attachment)
    app.router.add_post("/api/tasks/{task_id}/comments", api_add_comment)
    app.router.add_get("/api/stats", api_get_stats)
    app.router.add_get("/api/companies/{company_id}/speed_rating", api_speed_rating)
    app.router.add_post("/api/ai/chat", api_ai_chat)
    app.router.add_get("/api/ai/status", api_ai_status)
    app.router.add_post("/api/ai/confirm-task", api_ai_confirm_task)
    app.router.add_get("/api/avatar", api_get_avatar)
    app.router.add_get("/api/workflows", api_get_workflows)
    app.router.add_post("/api/workflows/{task_id}/start", api_workflow_step_start)
    app.router.add_post("/api/workflows/{task_id}/done", api_workflow_step_done)
    app.router.add_post("/api/workflows/steps/{step_id}/comment", api_workflow_step_comment)
    app.router.add_post("/api/workflows/steps/{step_id}/upload", api_workflow_step_upload)
    # Murojaat (taklif/shikoyat)
    app.router.add_get("/api/feedback/meta", api_feedback_meta)
    app.router.add_get("/api/feedback/my", api_feedback_my)
    app.router.add_get("/api/feedback/inbox", api_feedback_inbox)
    app.router.add_post("/api/feedback/upload", api_feedback_upload)
    app.router.add_post("/api/feedback", api_feedback_create)
    app.router.add_post("/api/feedback/{feedback_id}/reply", api_feedback_reply)
    app.router.add_post("/api/feedback/{feedback_id}/resolve", api_feedback_resolve)

    # Admin API routes (no Telegram auth required)
    app.router.add_post("/admin/api/login", admin_login)
    app.router.add_get("/admin/api/stats", admin_stats)
    app.router.add_get("/admin/api/users", admin_users)
    app.router.add_post("/admin/api/users/{user_id}/toggle-ban", admin_toggle_ban)
    app.router.add_post("/admin/api/users/{user_id}/toggle-hr", admin_toggle_hr)
    app.router.add_post("/admin/api/users/{user_id}/toggle-feedback-admin", admin_toggle_feedback_admin)
    app.router.add_post("/admin/api/users/{user_id}/toggle-ai", admin_toggle_ai)
    app.router.add_get("/admin/api/users/{user_id}/groups", admin_user_groups)
    app.router.add_get("/admin/api/users/{user_id}/activity", admin_user_activity)
    app.router.add_get("/admin/api/users/{user_id}/details", admin_user_details)
    app.router.add_delete("/admin/api/users/{user_id}", admin_delete_user)
    app.router.add_delete("/admin/api/groups/{group_id}/members/{user_id}", admin_remove_group_member)
    app.router.add_get("/admin/api/companies", admin_companies)
    app.router.add_delete("/admin/api/companies/{company_id}", admin_delete_company)
    app.router.add_get("/admin/api/groups", admin_groups)
    app.router.add_get("/admin/api/groups/{group_id}/members", admin_group_members)
    app.router.add_post("/admin/api/groups/{group_id}/toggle-block", admin_group_block_toggle)
    app.router.add_get("/admin/api/tasks", admin_tasks)
    app.router.add_get("/admin/api/tasks/{task_id}", admin_task_detail)
    app.router.add_get("/admin/api/users/{user_id}/late-tasks", admin_user_late_tasks)
    app.router.add_get("/admin/api/users/{user_id}/overdue-pending", admin_user_overdue_pending)
    app.router.add_patch("/admin/api/tasks/{task_id}", admin_update_task)
    app.router.add_patch("/admin/api/steps/{step_id}", admin_update_step)
    app.router.add_delete("/admin/api/tasks/{task_id}", admin_delete_task)

    # HR Panel routes
    app.router.add_get("/employee/api/my-docs", employee_my_docs)
    app.router.add_post("/employee/api/assignments/{assignment_id}/respond", employee_respond)
    app.router.add_get("/employee", serve_employee)
    app.router.add_get("/employee/", serve_employee)

    app.router.add_post("/hr/api/login", hr_login)
    app.router.add_get("/hr/api/stats", hr_stats)
    app.router.add_get("/hr/api/documents", hr_get_documents)
    app.router.add_post("/hr/api/documents", hr_create_document)
    app.router.add_get("/hr/api/documents/{doc_id}", hr_get_document)
    app.router.add_patch("/hr/api/documents/{doc_id}", hr_update_document)
    app.router.add_delete("/hr/api/documents/{doc_id}", hr_delete_document)
    app.router.add_post("/hr/api/documents/{document_id}/reminder", hr_set_reminder)
    app.router.add_get("/hr/api/users", hr_get_users)
    app.router.add_post("/hr/api/assignments", hr_assign_document)
    app.router.add_get("/hr/api/assignments", hr_get_assignments)
    app.router.add_post("/hr/api/assignments/{assignment_id}/remind", hr_remind_assignment)
    app.router.add_get("/hr/api/images/{filename}", hr_serve_image)
    app.router.add_get("/hr/api/feedback", hr_feedback_list)
    app.router.add_post("/hr/api/feedback/{feedback_id}/reply", hr_feedback_reply)
    app.router.add_post("/hr/api/feedback/{feedback_id}/resolve", hr_feedback_resolve)
    app.router.add_post("/hr/api/feedback/{feedback_id}/discuss", hr_feedback_discuss)
    app.router.add_get("/hr", serve_hr)
    app.router.add_get("/hr/", serve_hr)

    # Static files (webapp/)
    if WEBAPP_DIR.exists():
        app.router.add_static("/css", WEBAPP_DIR / "css", show_index=False)
        app.router.add_static("/js", WEBAPP_DIR / "js", show_index=False)
        app.router.add_static("/uploads", ATTACH_DIR, show_index=False)

        async def serve_index(request):
            return web.FileResponse(
                WEBAPP_DIR / "index.html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        app.router.add_get("/", serve_index)

        async def serve_admin(request):
            return web.FileResponse(
                WEBAPP_DIR / "admin.html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        app.router.add_get("/admin", serve_admin)

        async def serve_preview_ios(request):
            return web.FileResponse(
                WEBAPP_DIR / "preview-ios.html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        app.router.add_get("/preview-ios.html", serve_preview_ios)

    logger.info(f"API server tayyor (webapp: {WEBAPP_DIR})")
    return app
