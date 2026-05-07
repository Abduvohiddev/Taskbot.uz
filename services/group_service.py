"""
Group service - guruh va a'zolar bilan ishlash
"""
import logging
from typing import List, Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Group, GroupMember, User, UserRole, Task, TaskStatus

logger = logging.getLogger(__name__)


class GroupService:
    """Guruhlar bilan ishlash xizmati"""
    
    @staticmethod
    async def create_or_get_group(
        session: AsyncSession,
        telegram_group_id: int,
        name: str,
        owner_id: int,
        description: Optional[str] = None,
    ) -> Group:
        """Guruhni DB da topish yoki yaratish"""
        result = await session.execute(
            select(Group).where(Group.telegram_group_id == telegram_group_id)
        )
        group = result.scalar_one_or_none()
        
        if group:
            if group.name != name:
                group.name = name
            # Bot qayta qo'shilganda aktiv qilamiz
            if not group.is_active:
                group.is_active = True
                logger.info(f"Guruh qayta aktivlashtirildi: {group.id} - {group.name}")
            return group
        
        group = Group(
            telegram_group_id=telegram_group_id,
            name=name,
            description=description,
            owner_id=owner_id,
        )
        session.add(group)
        await session.flush()
        
        admin_member = GroupMember(
            group_id=group.id,
            user_id=owner_id,
            role=UserRole.ADMIN,
        )
        session.add(admin_member)
        await session.flush()
        
        logger.info(f"Yangi guruh yaratildi: {group.id} - {name}")
        return group
    
    @staticmethod
    async def get_group_by_telegram_id(
        session: AsyncSession, telegram_group_id: int
    ) -> Optional[Group]:
        """Telegram ID bo'yicha guruhni olish"""
        result = await session.execute(
            select(Group)
            .where(Group.telegram_group_id == telegram_group_id)
            .options(selectinload(Group.members).selectinload(GroupMember.user))
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_groups(
        session: AsyncSession, user_id: int
    ) -> List[Group]:
        """Foydalanuvchi a'zo bo'lgan guruhlar"""
        result = await session.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                and_(
                    GroupMember.user_id == user_id,
                    Group.is_active == True,
                )
            )
            .options(selectinload(Group.members))
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def add_member(
        session: AsyncSession,
        group_id: int,
        user_id: int,
        role: UserRole = UserRole.EXECUTOR,
    ) -> Optional[GroupMember]:
        """Guruhga a'zo qo'shish"""
        result = await session.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        
        member = GroupMember(group_id=group_id, user_id=user_id, role=role)
        session.add(member)
        await session.flush()
        logger.info(f"A'zo qo'shildi: group={group_id} user={user_id} role={role}")
        return member
    
    @staticmethod
    async def remove_member(
        session: AsyncSession,
        group_id: int,
        user_id: int,
    ) -> bool:
        """Guruhdan a'zoni o'chirish"""
        result = await session.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        
        await session.delete(member)
        return True
    
    @staticmethod
    async def change_member_role(
        session: AsyncSession,
        group_id: int,
        user_id: int,
        new_role: UserRole,
    ) -> bool:
        """A'zoning rolini o'zgartirish"""
        result = await session.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        
        member.role = new_role
        return True
    
    @staticmethod
    async def get_members(
        session: AsyncSession, group_id: int
    ) -> List[GroupMember]:
        """Guruh a'zolarini olish"""
        result = await session.execute(
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .options(selectinload(GroupMember.user))
            .order_by(GroupMember.role, GroupMember.joined_at)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_group_stats(
        session: AsyncSession, group_id: int
    ) -> dict:
        """Guruh statistikasini hisoblash"""
        result = await session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.group_id == group_id)
            .group_by(Task.status)
        )
        status_counts = {row[0].value: row[1] for row in result.all()}
        
        total = sum(status_counts.values())
        done = status_counts.get("done", 0)
        overdue = status_counts.get("overdue", 0)
        
        completion_rate = (done / total * 100) if total > 0 else 0
        
        members_count = await session.execute(
            select(func.count(GroupMember.id)).where(GroupMember.group_id == group_id)
        )
        
        return {
            "total_tasks": total,
            "status_counts": status_counts,
            "completion_rate": round(completion_rate, 1),
            "members_count": members_count.scalar() or 0,
            "overdue_count": overdue,
        }
