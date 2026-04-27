"""
Statistics service - statistika va hisobotlar
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Task, TaskStatus, TaskAssignment, User, GroupMember, Group
)

logger = logging.getLogger(__name__)


class StatsService:
    """Statistika va hisobotlar xizmati"""
    
    @staticmethod
    async def get_user_stats(
        session: AsyncSession,
        user_id: int,
        days: int = 30,
    ) -> Dict:
        """Foydalanuvchi statistikasi — per-user assignment status asosida"""
        since = datetime.utcnow() - timedelta(days=days)
        now = datetime.utcnow()

        # Per-user assignment status bo'yicha sanash
        result = await session.execute(
            select(TaskAssignment.status, func.count(TaskAssignment.id))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                and_(
                    TaskAssignment.user_id == user_id,
                    Task.created_at >= since,
                )
            )
            .group_by(TaskAssignment.status)
        )
        asg_counts = {row[0]: row[1] for row in result.all()}

        done = asg_counts.get("done", 0)
        in_progress = asg_counts.get("in_progress", 0) + asg_counts.get("review", 0)
        new_cnt = asg_counts.get("new", 0)

        # Overdue: foydalanuvchining o'zi bajarmagan va deadline o'tgan
        overdue_res = await session.execute(
            select(func.count(TaskAssignment.id))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                and_(
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.status != "done",
                    Task.deadline.isnot(None),
                    Task.deadline < now,
                    Task.created_at >= since,
                )
            )
        )
        overdue = overdue_res.scalar() or 0

        total = sum(asg_counts.values())
        completion_rate = (done / total * 100) if total > 0 else 0

        return {
            "total": total,
            "done": done,
            "overdue": overdue,
            "in_progress": in_progress,
            "new": new_cnt,
            "completion_rate": round(completion_rate, 1),
            "status_counts": {"done": done, "in_progress": in_progress, "new": new_cnt, "overdue": overdue},
        }
    
    @staticmethod
    async def get_group_member_stats(
        session: AsyncSession,
        group_id: int,
        days: int = 30,
    ) -> List[Dict]:
        """Guruh a'zolari bo'yicha statistika"""
        since = datetime.utcnow() - timedelta(days=days)
        
        members_result = await session.execute(
            select(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group_id)
        )
        members = list(members_result.scalars().all())
        
        stats = []
        for user in members:
            result = await session.execute(
                select(Task.status, func.count(Task.id))
                .join(TaskAssignment, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        Task.group_id == group_id,
                        Task.created_at >= since,
                    )
                )
                .group_by(Task.status)
            )
            status_counts = {row[0].value: row[1] for row in result.all()}
            
            stats.append({
                "user_id": user.id,
                "user_name": user.full_name,
                "done": status_counts.get("done", 0),
                "overdue": status_counts.get("overdue", 0),
                "in_progress": status_counts.get("in_progress", 0),
                "new": status_counts.get("new", 0),
                "total": sum(status_counts.values()),
            })
        
        stats.sort(key=lambda x: x["total"], reverse=True)
        return stats

    @staticmethod
    async def get_company_member_stats(
        session: AsyncSession,
        company_id: int,
    ) -> List[Dict]:
        """Kompaniya a'zolari statistika + reyting bali"""
        from database.models import CompanyMember, Company

        members_res = await session.execute(
            select(User, CompanyMember)
            .join(CompanyMember, CompanyMember.user_id == User.id)
            .where(CompanyMember.company_id == company_id)
        )
        members = list(members_res.all())

        now = datetime.utcnow()
        stats = []
        for user, member in members:
            # Per-user TaskAssignment statusi bo'yicha
            res = await session.execute(
                select(TaskAssignment.status, func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        Task.company_id == company_id,
                    )
                )
                .group_by(TaskAssignment.status)
            )
            sc = {row[0]: row[1] for row in res.all()}
            done       = sc.get("done", 0)
            in_progress= sc.get("in_progress", 0) + sc.get("review", 0)
            new        = sc.get("new", 0)
            total      = sum(sc.values())
            ov_res = await session.execute(
                select(func.count(TaskAssignment.id))
                .join(Task, TaskAssignment.task_id == Task.id)
                .where(
                    and_(
                        TaskAssignment.user_id == user.id,
                        TaskAssignment.status != "done",
                        Task.deadline.isnot(None),
                        Task.deadline < now,
                        Task.company_id == company_id,
                    )
                )
            )
            overdue = ov_res.scalar() or 0
            score      = max(0, done * 10 - overdue * 8 + in_progress * 2)
            rate       = round(done / total * 100) if total else 0

            stats.append({
                "user_id": user.id,
                "user_name": member.display_name or user.full_name,
                "role": member.role.value,
                "done": done,
                "overdue": overdue,
                "in_progress": in_progress,
                "new": new,
                "total": total,
                "score": score,
                "completion_rate": rate,
            })

        stats.sort(key=lambda x: x["score"], reverse=True)
        for i, s in enumerate(stats):
            s["rank"] = i + 1
        return stats

    @staticmethod
    async def get_user_priority_stats(
        session: AsyncSession,
        user_id: int,
        company_id: Optional[int] = None,
    ) -> Dict:
        """Foydalanuvchi vazifalarining muhimlik taqsimoti"""
        stmt = (
            select(Task.priority, func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(TaskAssignment.user_id == user_id)
            .group_by(Task.priority)
        )
        if company_id:
            stmt = stmt.where(Task.company_id == company_id)
        res = await session.execute(stmt)
        return {row[0].value: row[1] for row in res.all()}
    
    @staticmethod
    async def get_weekly_dynamics(
        session: AsyncSession,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        """Haftalik dinamika - har kun yaratilgan va bajarilgan"""
        now = datetime.utcnow()
        days_data = []
        
        day_names_uz = ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"]
        
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            created_query = select(func.count(Task.id)).where(
                Task.created_at.between(day_start, day_end)
            )
            completed_query = select(func.count(Task.id)).where(
                Task.completed_at.between(day_start, day_end)
            )
            
            if group_id:
                created_query = created_query.where(Task.group_id == group_id)
                completed_query = completed_query.where(Task.group_id == group_id)
            
            if user_id:
                created_query = created_query.join(
                    TaskAssignment, TaskAssignment.task_id == Task.id
                ).where(TaskAssignment.user_id == user_id)
                completed_query = completed_query.join(
                    TaskAssignment, TaskAssignment.task_id == Task.id
                ).where(TaskAssignment.user_id == user_id)
            
            created_count = (await session.execute(created_query)).scalar() or 0
            completed_count = (await session.execute(completed_query)).scalar() or 0
            
            days_data.append({
                "date": day_start.strftime("%d.%m"),
                "day": day_names_uz[day_start.weekday()],
                "created": created_count,
                "done": completed_count,
            })
        
        return days_data
    
    @staticmethod
    async def get_completion_report(
        session: AsyncSession,
        group_id: Optional[int] = None,
        days: int = 7,
    ) -> Dict:
        """Bajarilish hisoboti"""
        since = datetime.utcnow() - timedelta(days=days)
        
        query = select(func.count(Task.id)).where(Task.created_at >= since)
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_created = (await session.execute(query)).scalar() or 0
        
        query = select(func.count(Task.id)).where(
            and_(
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
            )
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_completed = (await session.execute(query)).scalar() or 0
        
        query = select(func.count(Task.id)).where(
            Task.status == TaskStatus.OVERDUE
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        total_overdue = (await session.execute(query)).scalar() or 0
        
        query = select(
            func.avg(
                func.extract('epoch', Task.completed_at - Task.created_at) / 3600
            )
        ).where(
            and_(
                Task.completed_at.isnot(None),
                Task.completed_at >= since,
            )
        )
        if group_id:
            query = query.where(Task.group_id == group_id)
        avg_hours = (await session.execute(query)).scalar() or 0
        
        return {
            "period_days": days,
            "total_created": total_created,
            "total_completed": total_completed,
            "total_overdue": total_overdue,
            "avg_completion_hours": round(float(avg_hours), 1) if avg_hours else 0,
            "completion_rate": round(
                (total_completed / total_created * 100) if total_created > 0 else 0, 1
            ),
        }
