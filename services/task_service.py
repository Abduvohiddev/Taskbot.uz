"""
Task service - vazifalar biznes logikasi
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Task, TaskStatus, Priority, User, Group, GroupMember,
    TaskAssignment, TaskComment, TaskHistory, UserRole
)
from config import settings

logger = logging.getLogger(__name__)


class TaskService:
    """Vazifalar bilan ishlash xizmati"""
    
    @staticmethod
    async def create_task(
        session: AsyncSession,
        title: str,
        creator_id: int,
        description: Optional[str] = None,
        priority: Priority = Priority.MEDIUM,
        deadline: Optional[datetime] = None,
        group_id: Optional[int] = None,
        company_id: Optional[int] = None,
        assignee_ids: Optional[List[int]] = None,
        responsible_user_id: Optional[int] = None,
        responsible_user_ids: Optional[List[int]] = None,
        parent_id: Optional[int] = None,
    ) -> Task:
        """Yangi vazifa yaratish"""
        # responsible_user_ids ustunlik oladi; eski responsible_user_id bilan ham ishlaydi
        resp_set: set = set(responsible_user_ids or [])
        if responsible_user_id and not resp_set:
            resp_set = {responsible_user_id}

        task = Task(
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            creator_id=creator_id,
            group_id=group_id,
            company_id=company_id,
            parent_id=parent_id,
            status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()

        if assignee_ids:
            for user_id in assignee_ids:
                is_resp = user_id in resp_set
                assignment = TaskAssignment(
                    task_id=task.id, user_id=user_id, is_responsible=is_resp
                )
                session.add(assignment)
        
        history = TaskHistory(
            task_id=task.id,
            user_id=creator_id,
            action="created",
            new_value={"title": title, "priority": priority.value},
        )
        session.add(history)
        
        await session.flush()
        logger.info(f"Vazifa yaratildi: {task.id} - {title[:30]}")
        return task
    
    @staticmethod
    async def get_task(
        session: AsyncSession, task_id: int, load_relations: bool = True
    ) -> Optional[Task]:
        """Bitta vazifani olish"""
        query = select(Task).where(Task.id == task_id)
        if load_relations:
            query = query.options(
                selectinload(Task.creator),
                selectinload(Task.group),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
                selectinload(Task.comments).selectinload(TaskComment.user),
                selectinload(Task.attachments),
                selectinload(Task.subtasks),
            )
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_tasks(
        session: AsyncSession,
        user_id: int,
        status: Optional[TaskStatus] = None,
        include_completed: bool = False,
    ) -> List[Task]:
        """Foydalanuvchining vazifalari"""
        query = (
            select(Task)
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(TaskAssignment.user_id == user_id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.group),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
            )
            .order_by(Task.deadline.asc().nullslast(), Task.created_at.desc())
        )
        
        if status:
            query = query.where(Task.status == status)
        elif not include_completed:
            query = query.where(
                Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])
            )
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_group_tasks(
        session: AsyncSession,
        group_id: int,
        status: Optional[TaskStatus] = None,
    ) -> List[Task]:
        """Guruhdagi barcha vazifalar"""
        query = (
            select(Task)
            .where(Task.group_id == group_id)
            .options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
            )
            .order_by(Task.created_at.desc())
        )
        
        if status:
            query = query.where(Task.status == status)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def update_task_status(
        session: AsyncSession,
        task_id: int,
        new_status: TaskStatus,
        user_id: int,
    ) -> Optional[Task]:
        """Vazifa statusini yangilash"""
        task = await TaskService.get_task(session, task_id)
        if not task:
            return None
        
        old_status = task.status
        task.status = new_status
        
        if new_status == TaskStatus.DONE:
            _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
            task.completed_at = datetime.now(_TZ)
        
        history = TaskHistory(
            task_id=task.id,
            user_id=user_id,
            action="status_changed",
            old_value={"status": old_status.value},
            new_value={"status": new_status.value},
        )
        session.add(history)
        
        logger.info(f"Vazifa statusi o'zgartirildi: {task_id} {old_status} -> {new_status}")
        return task
    
    @staticmethod
    async def get_overdue_tasks(
        session: AsyncSession,
        group_id: Optional[int] = None,
    ) -> List[Task]:
        """Kechikkan vazifalar"""
        _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
        now = datetime.now(_TZ)
        query = (
            select(Task)
            .where(
                and_(
                    Task.deadline < now,
                    Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
                )
            )
            .options(
                selectinload(Task.creator),
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
            )
            .order_by(Task.deadline.asc())
        )
        
        if group_id:
            query = query.where(Task.group_id == group_id)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_tasks_near_deadline(
        session: AsyncSession,
        hours: int = 24,
    ) -> List[Task]:
        """Deadline ga yaqin vazifalar"""
        _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
        now = datetime.now(_TZ)
        target = now + timedelta(hours=hours)
        
        query = (
            select(Task)
            .where(
                and_(
                    Task.deadline.between(now, target),
                    Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.OVERDUE]),
                    Task.warned_24h == False if hours >= 24 else Task.warned_1h == False,
                )
            )
            .options(
                selectinload(Task.assignments).selectinload(TaskAssignment.user),
            )
        )
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def add_comment(
        session: AsyncSession,
        task_id: int,
        user_id: int,
        content: str,
    ) -> TaskComment:
        """Vazifaga izoh qo'shish"""
        comment = TaskComment(
            task_id=task_id,
            user_id=user_id,
            content=content,
        )
        session.add(comment)
        await session.flush()
        return comment
    
    @staticmethod
    async def delete_task(
        session: AsyncSession,
        task_id: int,
        user_id: int,
    ) -> bool:
        """Vazifani o'chirish"""
        task = await TaskService.get_task(session, task_id, load_relations=False)
        if not task:
            return False
        
        await session.delete(task)
        logger.info(f"Vazifa o'chirildi: {task_id} foydalanuvchi {user_id} tomonidan")
        return True
    
    @staticmethod
    async def get_user_role_in_group(
        session: AsyncSession,
        user_id: int,
        group_id: int,
    ) -> Optional[UserRole]:
        """Foydalanuvchining guruhdagi roli"""
        result = await session.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.user_id == user_id,
                    GroupMember.group_id == group_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        return member.role if member else None
    
    @staticmethod
    async def is_user_assignee(
        session: AsyncSession,
        user_id: int,
        task_id: int,
    ) -> bool:
        """Foydalanuvchi vazifaga biriktirilganmi"""
        result = await session.execute(
            select(TaskAssignment).where(
                and_(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_user_assignment(
        session: AsyncSession,
        user_id: int,
        task_id: int,
    ) -> "Optional[TaskAssignment]":
        """Foydalanuvchining aniq TaskAssignment obyektini qaytaradi"""
        result = await session.execute(
            select(TaskAssignment).where(
                and_(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_assignment_status(
        session: AsyncSession,
        user_id: int,
        task_id: int,
        new_status: str,          # "in_progress" | "done"
    ) -> "Optional[TaskAssignment]":
        """Ijrochining SHAXSIY statusini o'zgartiradi.

        Faqat is_responsible=True bo'lgan ijrochilar o'zgartira oladi.
        Qaytaradi: yangilangan TaskAssignment yoki None (ruxsat yo'q / topilmadi).
        """
        result = await session.execute(
            select(TaskAssignment).where(
                and_(
                    TaskAssignment.task_id == task_id,
                    TaskAssignment.user_id == user_id,
                )
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment or not assignment.is_responsible:
            return None

        assignment.status = new_status
        if new_status == "done":
            _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)
            assignment.completed_at = datetime.now(_TZ)
        else:
            assignment.completed_at = None

        # Tarix yozuvi
        history = TaskHistory(
            task_id=task_id,
            user_id=user_id,
            action="assignment_status_changed",
            new_value={"assignment_status": new_status},
        )
        session.add(history)
        return assignment

    @staticmethod
    async def check_and_auto_complete(
        session: AsyncSession,
        task_id: int,
        changed_by_id: int,
    ) -> bool:
        """Barcha masul ijrochilar 'done' belgilaganmi?

        Agar ha bo'lsa — task.status = DONE ga o'tkazadi va True qaytaradi.
        Aks holda task.status = IN_PROGRESS qilib qo'yadi va False qaytaradi.
        """
        task = await TaskService.get_task(session, task_id)
        if not task:
            return False

        resp_assignments = [a for a in task.assignments if a.is_responsible]

        # Masul ijrochilar yo'q bo'lsa — yagona ijrochi ham masul hisoblanadi
        if not resp_assignments:
            resp_assignments = task.assignments

        all_done = resp_assignments and all(a.status == "done" for a in resp_assignments)

        _TZ = ZoneInfo(settings.DEFAULT_TIMEZONE)

        if all_done:
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now(_TZ)
            history = TaskHistory(
                task_id=task_id,
                user_id=changed_by_id,
                action="status_changed",
                old_value={"status": TaskStatus.IN_PROGRESS.value},
                new_value={"status": TaskStatus.DONE.value},
            )
            session.add(history)
            logger.info(f"Vazifa avtomatik yakunlandi: {task_id}")
        else:
            # Hech bo'lmaganda bitta in_progress bo'lsa — task ham in_progress
            any_in_progress = any(a.status == "in_progress" for a in resp_assignments)
            if any_in_progress and task.status == TaskStatus.NEW:
                task.status = TaskStatus.IN_PROGRESS
                history = TaskHistory(
                    task_id=task_id,
                    user_id=changed_by_id,
                    action="status_changed",
                    old_value={"status": TaskStatus.NEW.value},
                    new_value={"status": TaskStatus.IN_PROGRESS.value},
                )
                session.add(history)

        return all_done
