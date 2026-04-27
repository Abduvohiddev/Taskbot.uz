"""
Task service - vazifalar biznes logikasi
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Task, TaskStatus, Priority, User, Group, GroupMember,
    TaskAssignment, TaskComment, TaskHistory, UserRole
)

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
    ) -> Task:
        """Yangi vazifa yaratish"""
        task = Task(
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            creator_id=creator_id,
            group_id=group_id,
            company_id=company_id,
            status=TaskStatus.NEW,
        )
        session.add(task)
        await session.flush()
        
        if assignee_ids:
            for user_id in assignee_ids:
                assignment = TaskAssignment(task_id=task.id, user_id=user_id)
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
            task.completed_at = datetime.utcnow()
        
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
        now = datetime.utcnow()
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
        now = datetime.utcnow()
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
