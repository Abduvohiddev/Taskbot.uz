"""
Mini App uchun API server (aiohttp)
Static fayllar + REST API
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from aiohttp import web
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from api.auth import validate_init_data, validate_auth_token
from config import settings
from database.db import get_session
from database.models import (
    User, Task, TaskStatus, Priority, TaskAssignment,
    TaskHistory, TaskComment, TaskAttachment, GroupMember, Company, CompanyMember, CompanyRole,
    TaskStep, TaskStepComment, TaskStepAttachment, Group,
)
from services.notification_service import NotificationService
from services.ai_service import AIService

logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
_TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
_UTC = ZoneInfo("UTC")


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
    # Skip auth for static files
    if not request.path.startswith("/api"):
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

        stmt = select(Task).outerjoin(TaskAssignment, TaskAssignment.task_id == Task.id)

        if company_id_str == "all":
            # Hammasi: shaxsiy + barcha kompaniyalar + shu kompaniyalarga bog'liq guruhlar
            member_cos = await session.execute(
                select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
            )
            company_ids = [c[0] for c in member_cos.all()]

            # Shu kompaniyalarga bog'liq guruhlar (task.group_id bo'lgan, company_id yo'q tasklar)
            grp_res = await session.execute(
                select(Group.id).where(Group.company_id.in_(company_ids))
            ) if company_ids else None
            group_ids = [g[0] for g in grp_res.all()] if grp_res else []

            visibility_cond = [
                Task.company_id.is_(None),
                Task.company_id.in_(company_ids),
            ]
            if group_ids:
                visibility_cond.append(Task.group_id.in_(group_ids))

            stmt = stmt.where(or_(*visibility_cond)).where(
                or_(
                    Task.creator_id == user.id,
                    TaskAssignment.user_id == user.id,
                )
            )
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
            # Shaxsiy: company_id ham, group_id ham yo'q tasklar
            stmt = stmt.where(
                Task.company_id.is_(None),
                Task.group_id.is_(None),
            ).where(
                or_(
                    Task.creator_id == user.id,
                    TaskAssignment.user_id == user.id,
                )
            )
        # No filter — show all tasks

        result = await session.execute(
            stmt.options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.subtasks),
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


async def api_update_my_status(request):
    """Faqat joriy foydalanuvchi o'z assignment statusini yangilaydi.
    Hamma ijrochilar DONE bo'lganda Task umumiy statusi ham DONE bo'ladi.
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
        # Faqat mas'ul (is_responsible=True) status o'zgartira oladi
        if not assignment.is_responsible:
            raise web.HTTPForbidden(
                text=json.dumps({"error": "Siz bu vazifaning kuzatuvchisisiz. Faqat mas'ul shaxs status o'zgartira oladi."}),
                content_type="application/json",
            )

        old_my = assignment.status or "new"
        assignment.status = new_status.value
        assignment.completed_at = datetime.now(_UTC) if new_status == TaskStatus.DONE else None

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
        def _st(a):
            return a.status or "new"
        statuses = [_st(a) for a in assignments]

        new_task_status = old_task_status
        if statuses and all(s == "done" for s in statuses):
            new_task_status = TaskStatus.DONE
        elif any(s == "in_progress" for s in statuses):
            new_task_status = TaskStatus.IN_PROGRESS
        elif any(s == "review" for s in statuses):
            new_task_status = TaskStatus.REVIEW
        elif statuses and all(s in ("new", "cancelled") for s in statuses):
            new_task_status = TaskStatus.NEW

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

    return web.json_response({
        "ok": True,
        "my_status": new_status.value,
        "task_status": new_task_status.value,
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
            deadline = deadline.replace(tzinfo=None)
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

        stmt = select(Task.status, func.count(Task.id)).outerjoin(TaskAssignment, TaskAssignment.task_id == Task.id)

        if company_id_str == "all":
            member_cos = await session.execute(
                select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
            )
            company_ids = [c[0] for c in member_cos.all()]
            stmt = stmt.where(
                or_(Task.company_id.is_(None), Task.company_id.in_(company_ids))
            ).where(
                or_(Task.creator_id == user.id, TaskAssignment.user_id == user.id)
            )
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
            # CEO member_id filter
            if member_id_str and is_admin:
                target_uid = int(member_id_str)
                stmt = stmt.where(TaskAssignment.user_id == target_uid)
                # member ismini yuklaymiz
                usr_res = await session.execute(select(User).where(User.id == target_uid))
                target_usr = usr_res.scalar_one_or_none()
                if target_usr:
                    member_name = target_usr.full_name
        elif company_id_str == "personal":
            stmt = stmt.where(Task.company_id.is_(None)).where(
                or_(Task.creator_id == user.id, TaskAssignment.user_id == user.id)
            )
        else:
            stmt = stmt.where(
                or_(Task.creator_id == user.id, TaskAssignment.user_id == user.id)
            )

        result = await session.execute(stmt.group_by(Task.status))
        status_counts = {row[0].value: row[1] for row in result.all()}

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

    return web.json_response({
        "total": total,
        "new": status_counts.get("new", 0),
        "in_progress": status_counts.get("in_progress", 0),
        "review": status_counts.get("review", 0),
        "done": done,
        "overdue": status_counts.get("overdue", 0),
        "cancelled": status_counts.get("cancelled", 0),
        "completion_rate": completion_rate,
        "employee_stats": employee_stats,
        "is_admin": is_admin,
        "is_company": is_company,
        "member_name": member_name,   # agar CEO filter qo'llanilgan bo'lsa
    })


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
    from sqlalchemy import or_
    async with get_session() as session:
        stmt = select(Task).outerjoin(TaskAssignment, TaskAssignment.task_id == Task.id)
        if company_id_str and company_id_str != "personal":
            try:
                c_id_ctx = int(company_id_str)
                stmt = stmt.where(Task.company_id == c_id_ctx)
            except (ValueError, TypeError):
                stmt = stmt.where(Task.company_id.is_(None))
        else:
            stmt = stmt.where(Task.company_id.is_(None)).where(
                or_(Task.creator_id == user.id, TaskAssignment.user_id == user.id)
            )

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

    # --- AI ga jo'natamiz ---
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
                # Umumiy task statusini tekshirish
                all_asgn_res = await session.execute(
                    select(TaskAssignment).where(TaskAssignment.task_id == found_task.id)
                )
                all_asgn = all_asgn_res.scalars().all()
                statuses = [a.status or "new" for a in all_asgn]
                task_db_res = await session.execute(select(Task).where(Task.id == found_task.id))
                task_db = task_db_res.scalar_one()
                if statuses and all(s == "done" for s in statuses):
                    task_db.status = TaskStatus.DONE
                    task_db.completed_at = datetime.now(_UTC)
                elif any(s == "in_progress" for s in statuses):
                    task_db.status = TaskStatus.IN_PROGRESS
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
        companies = result.scalars().all()

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
        if not asg.is_responsible:
            return web.json_response({"error": "observer_only"}, status=403)

        old_status = asg.status
        started = False
        if asg.status in ("new", "pending", None):
            asg.status = "in_progress"
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
        if not asg.is_responsible:
            return web.json_response({"error": "observer_only"}, status=403)

        old_status = asg.status
        asg.status = "done"
        asg.completed_at = datetime.now(_UTC)

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

        # Check if all assignees done → task done
        all_done = all(a.status == "done" for a in all_assignees)
        if all_done:
            task.status = TaskStatus.DONE
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
                        "file_name": a.file_name,
                        "file_size": a.file_size,
                        "mime_type": a.mime_type,
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
            cur.status = "active"
            cur.started_at = datetime.now(_UTC)
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
            nxt.status = "active"
            nxt.started_at = _dt.utcnow()
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
            deadline = deadline.replace(tzinfo=None)
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

            step = TaskStep(
                task_id=task.id,
                title=step_title,
                order_index=idx,
                assignee_user_id=assignee_id,
                deadline=step_dl,
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
            # Task in_progress ga qachon o'tilganini history dan aniqlaymiz
            # Kimning statusini kim o'zgartirganidan qat'iy nazar, eng birinchi
            # in_progress vaqti barcha ijrochilar uchun ish boshlanish vaqti.
            hist_res = await session.execute(
                select(TaskHistory).where(
                    TaskHistory.task_id == task_id,
                    TaskHistory.action == "status_changed",
                )
                .order_by(TaskHistory.created_at.asc())
            )
            hist_entries = list(hist_res.scalars().all())
            # Birinchi in_progress vaqti
            task_done_at: Optional[datetime] = None
            for h in hist_entries:
                nv = h.new_value or {}
                if nv.get("status") == "in_progress" and task_started_at is None:
                    task_started_at = _aware(h.created_at)
                if nv.get("status") in ("done", "cancelled") and task_done_at is None:
                    task_done_at = _aware(h.created_at)

            asg_res = await session.execute(
                select(TaskAssignment).where(TaskAssignment.task_id == task_id)
                .options(selectinload(TaskAssignment.user))
            )
            for a in asg_res.scalars().all():
                # Ish boshlanish: task in_progress ga o'tilgan vaqt (aniqroq)
                # Aks holda assignment qilingan vaqtdan
                start = task_started_at or _aware(a.assigned_at)
                # Ish tugash: task done/cancelled bo'lgan vaqt yoki hozir
                end = task_done_at or now
                hours = _hrs(end - start) if start else 0.0
                uid = a.user_id
                if uid not in per_user:
                    per_user[uid] = {
                        "user_id": uid,
                        "name": a.user.full_name if a.user else f"User#{uid}",
                        "hours": 0.0,
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
    app.router.add_get("/api/tasks/{task_id}", api_get_task)
    app.router.add_get("/api/tasks/{task_id}/chart", api_get_task_chart)
    app.router.add_post("/api/tasks", api_create_task)
    app.router.add_post("/api/tasks/create-workflow", api_create_workflow)
    app.router.add_patch("/api/tasks/{task_id}/status", api_update_status)
    app.router.add_patch("/api/tasks/{task_id}/my-status", api_update_my_status)
    app.router.add_patch("/api/tasks/{task_id}/priority", api_update_priority)
    app.router.add_post("/api/tasks/{task_id}/start", api_task_start)
    app.router.add_post("/api/tasks/{task_id}/complete", api_task_complete)
    app.router.add_post("/api/tasks/{task_id}/attachments", api_upload_attachment)
    app.router.add_post("/api/tasks/{task_id}/comments", api_add_comment)
    app.router.add_get("/api/stats", api_get_stats)
    app.router.add_post("/api/ai/chat", api_ai_chat)
    app.router.add_post("/api/ai/confirm-task", api_ai_confirm_task)
    app.router.add_get("/api/avatar", api_get_avatar)
    app.router.add_get("/api/workflows", api_get_workflows)
    app.router.add_post("/api/workflows/{task_id}/start", api_workflow_step_start)
    app.router.add_post("/api/workflows/{task_id}/done", api_workflow_step_done)
    
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
